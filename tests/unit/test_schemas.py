import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatRequest
from app.schemas.users import LoginRequest, UserCreate, UserUpdate


def test_question_is_stripped():
    assert ChatRequest(question="  What is Redis?  ").question == "What is Redis?"


@pytest.mark.parametrize(
    "body",
    [
        {"question": ""},
        {"question": "   \n\t "},
        {"question": "x" * 4001},
        {"question": 42},
        {"question": "ok", "temperature": 1.5},
        {"question": "ok", "temperature": -0.1},
        {"question": "ok", "role": "ADMIN"},  # unknown fields are rejected
        {},
    ],
)
def test_invalid_chat_requests(body):
    with pytest.raises(ValidationError):
        ChatRequest(**body)


@pytest.mark.parametrize(
    "body",
    [
        {"username": "ab", "password": "long-enough-1"},
        {"username": "bad name!", "password": "long-enough-1"},
        {"username": "alice", "password": "short"},
        {"username": "alice", "password": "x" * 129},
    ],
)
def test_invalid_login_requests(body):
    with pytest.raises(ValidationError):
        LoginRequest(**body)


@pytest.mark.parametrize(
    "password",
    ["short1", "onlyletterslong", "12345678901234", "alice-Password-1"],
)
def test_weak_passwords_rejected_on_creation(password):
    with pytest.raises(ValidationError):
        UserCreate(username="alice", password=password)


def test_user_update_needs_a_field():
    with pytest.raises(ValidationError):
        UserUpdate()
    assert UserUpdate(is_active=False).is_active is False
