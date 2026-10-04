from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.tenant import Tenant, User
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.tenant import UserRead

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    # Deliberately the SAME error for "tenant doesn't exist", "email doesn't
    # exist", and "wrong password" — a different error per case would let an
    # attacker enumerate which tenant slugs or emails are valid.
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid tenant, email, or password"
    )

    tenant_result = await db.execute(select(Tenant).where(Tenant.slug == payload.tenant_slug))
    tenant = tenant_result.scalar_one_or_none()
    if tenant is None:
        raise invalid_credentials

    user_result = await db.execute(
        select(User).where(User.tenant_id == tenant.id, User.email == payload.email)
    )
    user = user_result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise invalid_credentials

    token = create_access_token(user_id=str(user.id), tenant_id=str(user.tenant_id), role=user.role.value)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: User = Depends(get_current_user)) -> UserRead:
    return current_user