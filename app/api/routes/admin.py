"""User administration (ADMIN only). Passwords and hashes are never returned."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import ContainerDep, require_role
from app.models import Role, User
from app.schemas.users import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/admin", tags=["admin"])
AdminUser = Annotated[User, Depends(require_role(Role.ADMIN))]


@router.get("/users", response_model=list[UserOut])
async def list_users(
    container: ContainerDep,
    _: AdminUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1000)] = 0,
) -> list[UserOut]:
    users = await container.user_service.list(limit, offset)
    return [UserOut.model_validate(u, from_attributes=True) for u in users]


@router.get("/audit", summary="Audit trail of admin actions, newest first")
async def list_audit_events(
    container: ContainerDep,
    _: AdminUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1000)] = 0,
) -> list[dict]:
    return await container.audit.list(limit, offset)


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(payload: UserCreate, container: ContainerDep, admin: AdminUser) -> UserOut:
    user = await container.user_service.create(payload, admin)
    return UserOut.model_validate(user, from_attributes=True)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str, payload: UserUpdate, container: ContainerDep, admin: AdminUser
) -> UserOut:
    user = await container.user_service.update(user_id, payload, admin)
    return UserOut.model_validate(user, from_attributes=True)
