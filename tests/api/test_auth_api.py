"""Authentication, RBAC matrix and admin routes through the real ASGI app."""

import time

import jwt
import pytest

from app.models import Role
from tests.conftest import TEST_PASSWORD, TEST_SECRET


async def test_login_success_and_me(harness):
    response = await harness.client.post(
        "/auth/login", json={"username": "alice", "password": TEST_PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 1800
    assert response.headers["x-request-id"]

    me = await harness.client.get(
        "/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["username"] == "alice" and me.json()["role"] == "USER"
    assert "password" not in me.text  # neither the password nor its hash is ever returned
    assert me.json()["last_login_at"] is not None


async def test_login_failures_share_one_generic_message(harness):
    await harness.add_user("sleeper", Role.USER, active=False)
    bodies = []
    for username, password in [
        ("alice", "wrong-password"),  # wrong password
        ("nobody", TEST_PASSWORD),  # unknown user
        ("sleeper", TEST_PASSWORD),  # inactive user
    ]:
        response = await harness.client.post(
            "/auth/login", json={"username": username, "password": password}
        )
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        bodies.append(response.json()["error"])
    assert {(b["code"], b["message"]) for b in bodies} == {
        ("INVALID_CREDENTIALS", "Invalid username or password.")
    }


async def test_login_validation_error_uses_envelope_without_echoing_input(harness):
    response = await harness.client.post(
        "/auth/login", json={"username": "a", "password": "super-secret-value"}
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR" and error["details"][0]["field"] == "username"
    assert "super-secret-value" not in response.text


async def test_login_throttling_locks_after_repeated_failures(harness):
    for _ in range(3):  # login_max_attempts=3 in the test settings
        response = await harness.client.post(
            "/auth/login", json={"username": "alice", "password": "wrong-password"}
        )
        assert response.status_code == 401
    locked = await harness.client.post(
        "/auth/login", json={"username": "alice", "password": TEST_PASSWORD}
    )
    assert locked.status_code == 429  # even the correct password is refused while locked
    assert int(locked.headers["retry-after"]) >= 1
    assert locked.json()["error"]["code"] == "RATE_LIMITED"


async def test_login_fails_closed_when_redis_is_down(harness):
    harness.redis_server.connected = False
    response = await harness.client.post(
        "/auth/login", json={"username": "alice", "password": TEST_PASSWORD}
    )
    assert response.status_code == 503


def _token(**overrides) -> str:
    claims = {"sub": "x", "role": "ADMIN", "iat": time.time(), "exp": time.time() + 600, "jti": "j"}
    claims.update(overrides)
    return jwt.encode(claims, overrides.pop("_secret", TEST_SECRET), algorithm="HS256")


@pytest.mark.parametrize(
    "headers",
    [
        {},  # missing token
        {"Authorization": "Bearer not-a-jwt"},  # malformed
        {"Authorization": "Basic YWxpY2U6cGFzcw=="},  # wrong scheme
        {"Authorization": "Bearer " + jwt.encode({"sub": "x"}, "wrong-secret-" * 4)},  # bad sig
        {"Authorization": "Bearer " + _token(exp=time.time() - 10)},  # expired
        {"Authorization": "Bearer " + _token()},  # valid signature, user does not exist
    ],
)
async def test_protected_route_returns_401(harness, headers):
    response = await harness.client.post("/chat", json={"question": "hi"}, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


async def test_deactivated_user_token_stops_working_immediately(harness):
    headers = await harness.auth("alice")
    assert (await harness.client.get("/auth/me", headers=headers)).status_code == 200
    user = await harness.users.get_by_username("alice")
    await harness.users.update_fields(user.id, {"is_active": False})
    # Policy: an inactive account can no longer authenticate => 401 (not 403).
    assert (await harness.client.get("/auth/me", headers=headers)).status_code == 401


async def test_role_comes_from_database_not_from_token(harness):
    """A token minted with role=ADMIN for a USER account gains nothing."""
    alice = await harness.users.get_by_username("alice")
    forged_role = {"Authorization": "Bearer " + _token(sub=alice.id, role="ADMIN")}
    assert (await harness.client.get("/admin/users", headers=forged_role)).status_code == 403


# RBAC matrix: (method, path, body) -> expected status per role
MATRIX = [
    ("POST", "/chat", {"question": "hi"}, {"admin1": 200, "alice": 200, "reader": 403}),
    ("GET", "/auth/me", None, {"admin1": 200, "alice": 200, "reader": 200}),
    ("GET", "/chat/history", None, {"admin1": 200, "alice": 200, "reader": 200}),
    ("GET", "/chat/history?user_id=all", None, {"admin1": 200, "alice": 403, "reader": 403}),
    ("GET", "/admin/users", None, {"admin1": 200, "alice": 403, "reader": 403}),
    (
        "POST",
        "/admin/users",
        {"username": "newbie", "password": "Str0ng-enough-pw"},
        {"admin1": 201, "alice": 403, "reader": 403},
    ),
    ("GET", "/metrics", None, {"admin1": 200, "alice": 403, "reader": 403}),
    ("GET", "/documents", None, {"admin1": 200, "alice": 200, "reader": 200}),
    ("POST", "/documents/search", {"query": "redis"}, {"admin1": 200, "alice": 200, "reader": 200}),
    (
        "POST",
        "/documents",
        {"title": "T", "text": "Redis is an in-memory store."},
        {"admin1": 201, "alice": 403, "reader": 403},
    ),
    ("DELETE", "/documents/does-not-exist", None, {"admin1": 404, "alice": 403, "reader": 403}),
]


@pytest.mark.parametrize(("method", "path", "body", "expected"), MATRIX)
async def test_rbac_matrix(harness, method, path, body, expected):
    for username, status in expected.items():
        response = await harness.client.request(
            method, path, json=body, headers=await harness.auth(username)
        )
        assert response.status_code == status, f"{username} {method} {path}: {response.text}"
        if status == 403:
            assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_admin_user_lifecycle(harness):
    admin = await harness.auth("admin1")
    created = await harness.client.post(
        "/admin/users",
        json={"username": "bob", "password": "Str0ng-enough-pw", "role": "READ_ONLY"},
        headers=admin,
    )
    assert created.status_code == 201 and "password" not in created.text
    bob_id = created.json()["id"]

    duplicate = await harness.client.post(
        "/admin/users", json={"username": "BOB", "password": "Str0ng-enough-pw"}, headers=admin
    )
    assert duplicate.status_code == 409  # usernames are unique, case-insensitively

    weak = await harness.client.post(
        "/admin/users", json={"username": "carol", "password": "weakweakweak"}, headers=admin
    )
    assert weak.status_code == 422

    promoted = await harness.client.patch(
        f"/admin/users/{bob_id}", json={"role": "USER"}, headers=admin
    )
    assert promoted.status_code == 200 and promoted.json()["role"] == "USER"

    listed = await harness.client.get("/admin/users", headers=admin)
    assert "bob" in [u["username"] for u in listed.json()]

    missing = await harness.client.patch(
        "/admin/users/00000000-0000-0000-0000-000000000000", json={"role": "USER"}, headers=admin
    )
    assert missing.status_code == 404


async def test_admin_cannot_lock_themselves_out(harness):
    admin = await harness.auth("admin1")
    me = (await harness.client.get("/auth/me", headers=admin)).json()
    for change in ({"is_active": False}, {"role": "USER"}):
        response = await harness.client.patch(
            f"/admin/users/{me['id']}", json=change, headers=admin
        )
        assert response.status_code == 422
