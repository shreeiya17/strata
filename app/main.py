from fastapi import FastAPI
from app.api.routes import auth, tenants
from app.api.routes import tenants
from app.core.config import settings

app = FastAPI(title=settings.app_name)

app.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
app.include_router(auth.router, prefix="/auth", tags=["auth"]) 

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}