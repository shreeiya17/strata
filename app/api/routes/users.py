from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.security import hash_password
from app.db.session import get_db
from app.models.tenant import User, UserRole
from app.schemas.tenant import UserCreateByAdmin, UserRead

router = APIRouter()


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateByAdmin,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> UserRead:
    """
    Admin-only. Note the new user is created with current_user.tenant_id,
    NEVER a tenant_id taken from the request body — an admin can only ever
    add users to their own tenant, not anyone else's. That's the actual
    enforcement point for isolation on writes.
    """
    new_user = User(
        tenant_id=current_user.tenant_id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(new_user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use for this tenant")
    await db.refresh(new_user)
    return new_user


@router.get("", response_model=list[UserRead])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[User]:
    """
    Any authenticated role can list — but note the explicit
    .where(User.tenant_id == current_user.tenant_id). This is the
    query-level half of tenant isolation: the FK constraint stops bad
    WRITES, but nothing stops a route from forgetting to filter on READS
    unless every query explicitly scopes by the current user's tenant.
    Forgetting this line is the single most common multi-tenant data leak.
    """
    result = await db.execute(select(User).where(User.tenant_id == current_user.tenant_id))
    return list(result.scalars().all())