import base64
import json
import time

import jwt
import pytest
from pydantic import ValidationError

from app.core.config import DEV_JWT_SECRET, Settings
from app.core.errors import AuthenticationError
from app.core.logging import redact
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from tests.conftest import TEST_SECRET, make_settings


def test_password_hash_roundtrip_and_salting():
    first, second = hash_password("Correct-Horse-42"), hash_password("Correct-Horse-42")
    assert first.startswith("$argon2id$")
    assert first != second  # a fresh random salt per hash
    assert verify_password("Correct-Horse-42", first)
    assert not verify_password("wrong-password", first)
    assert not verify_password("anything", "not-a-valid-hash")


def test_token_roundtrip_contains_required_claims():
    settings = make_settings()
    token, expires_in = create_access_token(user_id="u1", role="USER", settings=settings)
    claims = decode_access_token(token, settings)
    assert claims["sub"] == "u1" and claims["role"] == "USER"
    assert {"iat", "exp", "jti"} <= claims.keys()
    assert expires_in == settings.jwt_expire_minutes * 60


def test_expired_token_rejected():
    settings = make_settings()
    expired = jwt.encode(
        {"sub": "u1", "iat": time.time() - 120, "exp": time.time() - 60, "jti": "x"},
        TEST_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(AuthenticationError) as excinfo:
        decode_access_token(expired, settings)
    assert excinfo.value.code == "TOKEN_EXPIRED"


def test_tampered_payload_and_wrong_secret_rejected():
    settings = make_settings()
    token, _ = create_access_token(user_id="u1", role="USER", settings=settings)
    header, payload, signature = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["role"] = "ADMIN"  # privilege escalation attempt
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    with pytest.raises(AuthenticationError):
        decode_access_token(f"{header}.{forged}.{signature}", settings)

    other = jwt.encode(claims, "another-secret-that-is-also-long-enough-123", algorithm="HS256")
    with pytest.raises(AuthenticationError):
        decode_access_token(other, settings)


def test_alg_none_token_rejected():
    settings = make_settings()

    def b64(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    claims = {"sub": "u1", "role": "ADMIN", "iat": 1, "exp": time.time() + 600, "jti": "x"}
    unsigned = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(claims)}."
    with pytest.raises(AuthenticationError):
        decode_access_token(unsigned, settings)


def test_token_missing_required_claim_rejected():
    settings = make_settings()
    token = jwt.encode({"sub": "u1", "exp": time.time() + 600}, TEST_SECRET, algorithm="HS256")
    with pytest.raises(AuthenticationError):
        decode_access_token(token, settings)


@pytest.mark.parametrize("secret", [DEV_JWT_SECRET, "short"])
def test_prod_refuses_weak_jwt_secret(secret):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="prod", jwt_secret=secret)
    assert Settings(_env_file=None, app_env="prod", jwt_secret="x" * 32).app_env == "prod"


def test_log_redaction_removes_secrets():
    line = redact(
        'Authorization: Bearer abcdefghijklmnop password="hunter2secret" key sk-abcdefgh12345678'
    )
    assert "abcdefghijklmnop" not in line
    assert "hunter2secret" not in line
    assert "sk-abcdefgh12345678" not in line
