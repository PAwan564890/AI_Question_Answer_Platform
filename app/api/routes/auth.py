"""Authentication routes. Routes validate input and delegate to services."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import ContainerDep, CurrentUser, client_ip
from app.schemas.users import LoginRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse, summary="Exchange credentials for a JWT")
async def login(
    payload: LoginRequest, container: ContainerDep, ip: Annotated[str, Depends(client_ip)]
) -> TokenResponse:
    return await container.auth_service.login(payload.username, payload.password, ip)


@router.get("/me", response_model=UserOut, summary="Who am I? (any authenticated role)")
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user, from_attributes=True)
