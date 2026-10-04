# Strata

*A multi-tenant RAG knowledge platform with tenant-isolated auth, hybrid retrieval, and evaluation-backed search quality.*

A production-grade backend exploring what it actually takes to serve multiple
isolated tenants from one system: enforced data isolation at the schema
level, JWT auth scoped per-tenant, and (coming up) role-based access control
and retrieval-augmented search with measured, not assumed, quality.

## Setup (zsh, macOS)

```zsh
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install fastapi "uvicorn[standard]" "sqlalchemy>=2.0" asyncpg alembic \
  pydantic "pydantic[email]" pydantic-settings "python-jose[cryptography]" \
  bcrypt python-multipart greenlet

# 3. Postgres — this project was built and tested against a local Homebrew
#    install, not Docker (Docker Desktop wasn't running during development,
#    so that path is untested — use it if you prefer containers, but the
#    Homebrew path below is the one that's actually verified working):
brew install postgresql@14
brew services start postgresql@14
createdb strata

#    Docker is the more portable alternative if you have the daemon running:
#    docker run --name strata-postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=strata -p 5432:5432 -d postgres:16

# 4. Copy env template and fill in DATABASE_URL + JWT_SECRET_KEY
cp .env.example .env
#    Homebrew's Postgres uses trust auth under your Mac username by default
#    (no password) — set DATABASE_URL to:
#      postgresql+asyncpg://<your-username>@localhost:5432/strata
#    (run `whoami` if you're not sure what your username is)
#    If you used the Docker command above instead, use the postgres:postgres
#    credentials already in .env.example.

# 5. Apply the database migration
alembic upgrade head

# 6. Run the dev server
uvicorn app.main:app --reload
```

Confirm it's alive:

```zsh
curl -s http://localhost:8000/health
```

You should get back `{"status":"ok","environment":"development"}`.

## Current endpoints

| Method | Path | What it does |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `POST` | `/tenants/register` | Creates a new tenant + its first admin user, atomically |
| `POST` | `/auth/login` | Verifies credentials within a tenant, issues a JWT |
| `GET` | `/auth/me` | Returns the current user, resolved from the JWT |

Full interactive docs (request/response schemas, try-it-out): `/docs`.

## What's done vs. what's next

| Done | Not yet |
|---|---|
| Project structure, async FastAPI app | RBAC enforcement (`require_role(...)` dependency) |
| `Tenant` / `User` models, tenant isolation enforced via `TenantScopedMixin` | Document ingestion pipeline (chunking, embeddings) |
| Alembic migration — real Postgres schema, not just Python classes | pgvector + hybrid retrieval |
| Tenant registration (atomic tenant + admin user creation) | Redis semantic caching |
| JWT auth — login scoped per-tenant, protected routes via `get_current_user` | Evaluation harness (precision/recall against a labeled set) |
| Password hashing via `bcrypt` directly (not `passlib`, which is unmaintained and breaks against modern bcrypt) | React frontend |

## Why `TenantScopedMixin` exists

Every table holding tenant data inherits `tenant_id` as a required,
indexed foreign key — there's no code path to insert a row without an
owning tenant. That's the actual mechanism behind "tenant data is
isolated," not just something claimed in a README.

## Why login requires a tenant slug

A user's email is only unique *within* their tenant (enforced by a
composite `UniqueConstraint` on `(tenant_id, email)`), not globally — two
different tenants can each have a user with the same email. So login takes
`tenant_slug` + `email` + `password`, not just email + password.

## Folder layout

```
app/
  core/         — settings, password hashing, JWT encode/decode
  db/           — engine, session, declarative base + mixins
  models/       — SQLAlchemy models (Tenant, User)
  schemas/      — Pydantic request/response models
  api/
    deps.py     — shared dependencies (get_current_user)
    routes/     — one router per resource (tenants, auth)
migrations/     — Alembic migration scripts
```