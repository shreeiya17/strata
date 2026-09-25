from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(title=settings.app_name)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


# Day 5-6: mount auth + tenant routers here, e.g.
# from app.api.routes import auth
# app.include_router(auth.router, prefix="/auth", tags=["auth"])
