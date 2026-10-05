import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.tenant import User, UserRole

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise unauthorized

    user_id = payload.get("sub")
    if user_id is None:
        raise unauthorized

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise unauthorized

    # Defense in depth: even if a token were somehow issued with a stale
    # tenant_id, re-derive isolation from the DB row itself, not just the
    # token's claim. The token is a cache of identity, not the source of truth.
    return user

def require_role(*allowed_roles: UserRole):
    """
    Dependency FACTORY, not a dependency itself — call it with the roles
    a route allows, e.g. Depends(require_role(UserRole.ADMIN)). Returns a
    dependency that reuses get_current_user (so you get both identity AND
    the role check from one Depends call) and 403s if the user's role
    isn't in the allowed set.
    """

    async def _check_role(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(r.value for r in allowed_roles)}",
            )
        return current_user

    return _check_role