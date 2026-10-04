from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import get_db
from app.models.tenant import Tenant, User, UserRole
from app.schemas.tenant import TenantRegister, TenantRegisterResponse

router = APIRouter()


@router.post("/register", response_model=TenantRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_tenant(payload: TenantRegister, db: AsyncSession = Depends(get_db)) -> TenantRegisterResponse:
    """
    Creates a new tenant and its first user as an admin, in one request.
    This is the ONLY route that creates a user without an existing admin's
    approval — every other user-creation path (Day 5+) requires an
    authenticated admin of that tenant.
    """
    existing = await db.execute(select(Tenant).where(Tenant.slug == payload.tenant.slug))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant slug already taken")

    tenant = Tenant(name=payload.tenant.name, slug=payload.tenant.slug)
    db.add(tenant)
    await db.flush()  # assigns tenant.id without committing yet

    admin_user = User(
        tenant_id=tenant.id,
        email=payload.admin.email,
        hashed_password=hash_password(payload.admin.password),
        role=UserRole.ADMIN,
    )
    db.add(admin_user)

    await db.commit()
    await db.refresh(tenant)
    await db.refresh(admin_user)

    return TenantRegisterResponse(tenant=tenant, admin=admin_user)