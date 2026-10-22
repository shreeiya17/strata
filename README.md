# Strata

*A multi-tenant RAG knowledge platform with tenant-isolated auth, hybrid retrieval, and evaluation-backed search quality.*

A production-grade backend exploring what it actually takes to serve multiple
isolated tenants from one system: enforced data isolation at the schema
level, per-tenant JWT auth with role-based access control, and (in progress)
retrieval-augmented search with measured, not assumed, quality.

## Setup (zsh, macOS)

```zsh
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies. sentence-transformers pulls in PyTorch, so this
#    is a large install; the embedding model (~90MB) downloads on first use.
pip install fastapi "uvicorn[standard]" "sqlalchemy>=2.0" asyncpg alembic \
  pydantic "pydantic[email]" pydantic-settings "python-jose[cryptography]" \
  bcrypt python-multipart greenlet pgvector sentence-transformers

# 3. Postgres 17 + pgvector — built and tested against a local Homebrew
#    install. (Not 14: Homebrew's pgvector only supports 17 and 18.)
brew install postgresql@17 pgvector
brew services start postgresql@17
echo 'export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc          # postgresql@17 is keg-only, so it needs the PATH entry
createdb strata

#    Docker is untested here. If you prefer containers, use an image that
#    bundles pgvector (plain postgres images do NOT):
#    docker run --name strata-postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=strata -p 5432:5432 -d pgvector/pgvector:pg17

# 4. Copy env template and fill in DATABASE_URL + JWT_SECRET_KEY
cp .env.example .env
#    Homebrew's Postgres uses trust auth under your Mac username by default
#    (no password) — set DATABASE_URL to:
#      postgresql+asyncpg://<your-username>@localhost:5432/strata
#    (run `whoami` if you're not sure what your username is)
#    If you used the Docker command above instead, use the postgres:postgres
#    credentials already in .env.example.

# 5. Apply the database migrations (this also enables the pgvector extension)
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

| Method | Path | Auth | What it does |
|---|---|---|---|
| `GET` | `/health` | none | Liveness check |
| `POST` | `/tenants/register` | none | Creates a new tenant + its first admin user, atomically |
| `POST` | `/auth/login` | none | Verifies credentials within a tenant, issues a JWT |
| `GET` | `/auth/me` | any role | Returns the current user, resolved from the JWT |
| `POST` | `/users` | admin | Creates a user (with a role) inside the admin's own tenant |
| `GET` | `/users` | any role | Lists users in the caller's tenant only |

Full interactive docs (request/response schemas, try-it-out): `/docs`.

## What's done vs. what's next

| Done | Not yet |
|---|---|
| Async FastAPI app, Alembic migrations against real Postgres | Upload endpoint + background ingestion worker |
| `Tenant` / `User` models, tenant isolation via `TenantScopedMixin` | Hybrid (keyword + vector) retrieval |
| Tenant registration (atomic tenant + admin user creation) | Redis semantic caching |
| JWT auth, login scoped per tenant | Evaluation harness (precision/recall on a labeled query set) |
| RBAC (`require_role`) and tenant-scoped queries, verified across two tenants | Automated tests + CI |
| `documents` / `document_chunks` schema with a `vector(384)` column (pgvector) | React frontend |
| Paragraph-aware text chunker with overlap | |
| Local embedding service (`all-MiniLM-L6-v2`, no API key or cost) | |

## Design notes

**`TenantScopedMixin`.** Every table holding tenant data inherits `tenant_id`
as a required, indexed foreign key — there's no code path to insert a row
without an owning tenant. That's the mechanism behind "tenant data is
isolated," not just a claim.

**Login takes a tenant slug.** A user's email is only unique *within* their
tenant (a composite `UniqueConstraint` on `(tenant_id, email)`), so login
takes `tenant_slug` + `email` + `password`.

**Chunks carry their own `tenant_id`.** It's redundant with the parent
document's, on purpose: vector searches run against `document_chunks`, so the
tenant filter sits directly on the table being searched. When tested with two
tenants holding identical vectors, removing that filter leaked the other
tenant's chunk into the results; with it, nothing crossed over.

**Local embeddings.** `all-MiniLM-L6-v2` (384 dimensions) runs on CPU with no
API key. It truncates input beyond ~256 word-pieces, so chunks default to 800
characters.

**Exact vector search for now.** No approximate index yet, so search has
perfect recall. An index will be added later and its effect on recall and
latency measured.

## Folder layout

```
app/
  core/         — settings, password hashing, JWT encode/decode
  db/           — engine, session, declarative base + mixins
  models/       — SQLAlchemy models (Tenant, User, Document, DocumentChunk)
  schemas/      — Pydantic request/response models
  services/     — chunking, embeddings
  api/
    deps.py     — shared dependencies (get_current_user, require_role)
    routes/     — one router per resource (tenants, auth, users)
migrations/     — Alembic migration scripts
```