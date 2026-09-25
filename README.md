# Strata — Day 1 skeleton

*A multi-tenant RAG knowledge platform with tenant-isolated auth, hybrid retrieval, and evaluation-backed search quality.*

Multi-tenant, production-grade RAG knowledge platform. This is the Day 1
scaffold: Python/Poetry setup + a FastAPI app that boots, with the
tenant-isolation model already in the schema (see `app/db/base.py` and
`app/models/tenant.py`) so Days 4–6 (schema, auth, RBAC) build on a real
foundation instead of retrofitting it.

## Setup (zsh, macOS)

```zsh
# 1. Install Poetry if you don't have it
curl -sSL https://install.python-poetry.org | python3 -

# 2. Install dependencies (creates a .venv inside the project)
cd strata
poetry config virtualenvs.in-project true
poetry install

# 3. Postgres — easiest is Docker if you don't have it running locally
docker run --name strata-postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=strata -p 5432:5432 -d postgres:16

# 4. Copy env template and fill in JWT_SECRET_KEY with any long random string
cp .env.example .env

# 5. Run the dev server
poetry run uvicorn app.main:app --reload
```

Confirm it's alive:

```zsh
curl -s http://localhost:8000/health
```

You should get back `{"status":"ok","environment":"development"}`.

## What's here vs. what's next

| Done (Day 1) | Not yet (Days 3–6) |
|---|---|
| Project structure + Poetry config | FastAPI routes beyond `/health` |
| Settings loaded from `.env` | Alembic migration to actually create tables |
| Async DB session dependency | JWT auth (`app/api/routes/auth.py`) |
| `Tenant` / `User` models with tenant isolation baked into the base model | RBAC dependency (`require_role(...)`) |

## Why `TenantScopedMixin` exists

Every table holding tenant data inherits `tenant_id` as a required,
indexed foreign key — there's no code path to insert a row without an
owning tenant. That's the actual mechanism behind "tenant data is
isolated," not just something claimed in a README.

## Folder layout

```
app/
  core/     — settings, (later) security utilities
  db/       — engine, session, declarative base + mixins
  models/   — SQLAlchemy models
  schemas/  — Pydantic request/response models (Day 3+)
  api/      — routers, one file per resource (Day 3+)
  services/ — business logic kept out of route handlers
```
