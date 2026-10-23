from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import auth, documents, tenants, users
from app.core.config import settings
from app.core.queue import close_queue


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Shutdown: release the Redis connection if the API ever opened one.
    await close_queue()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(documents.router, prefix="/documents", tags=["documents"])


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}