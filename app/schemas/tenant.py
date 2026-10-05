import uuid

from pydantic import BaseModel, EmailStr, Field

from app.models.tenant import UserRole


# --- Tenant ---


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")


class TenantRead(BaseModel):
    id: uuid.UUID
    name: str
    slug: str

    model_config = {"from_attributes": True}  # lets us return an ORM object directly


# --- User ---


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: UserRole
    tenant_id: uuid.UUID

    model_config = {"from_attributes": True}

# --- Admin-created users within an existing tenant (Day 6: RBAC) ---


class UserCreateByAdmin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.VIEWER

# --- Combined: registering a brand-new tenant + its first admin user together ---


class TenantRegister(BaseModel):
    tenant: TenantCreate
    admin: UserCreate


class TenantRegisterResponse(BaseModel):
    tenant: TenantRead
    admin: UserRead