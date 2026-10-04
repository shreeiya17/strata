from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


def hash_password(plain_password: str) -> str:
    # bcrypt's own hard limit is 72 bytes of input — reject anything longer
    # with a clear error instead of silently truncating a user's password.
    if len(plain_password.encode("utf-8")) > 72:
        raise ValueError("Password must be 72 bytes or fewer")
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def create_access_token(*, user_id: str, tenant_id: str, role: str) -> str:
    """
    Encodes the three claims every protected route will need to check:
    - sub: which user
    - tenant_id: which tenant's data they're allowed to touch (Day 6 RBAC
      uses this to enforce isolation at the query level, not just at login)
    - role: what they're allowed to do within that tenant
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": user_id, "tenant_id": tenant_id, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None