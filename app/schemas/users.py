"""Request/response models for authentication and user administration."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models import Role

Username = Annotated[
    str, StringConstraints(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
]


def _check_password_strength(password: str, username: str | None) -> None:
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters long.")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise ValueError("Password must contain at least one letter and one digit.")
    if username and username.lower() in password.lower():
        raise ValueError("Password must not contain the username.")


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Username
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int


class UserOut(BaseModel):
    """What the API returns about a user. There is deliberately no password field."""

    id: str
    username: str
    role: Role
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Username
    password: str = Field(min_length=10, max_length=128)
    role: Role = Role.USER

    @model_validator(mode="after")
    def _strong_password(self) -> "UserCreate":
        _check_password_strength(self.password, self.username)
        return self


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=128)

    @model_validator(mode="after")
    def _validate(self) -> "UserUpdate":
        if self.role is None and self.is_active is None and self.password is None:
            raise ValueError("Provide at least one of: role, is_active, password.")
        if self.password is not None:
            _check_password_strength(self.password, None)
        return self
