# Strata

*A multi-tenant RAG knowledge platform with tenant-isolated auth, hybrid retrieval, and evaluation-backed search quality.*

A production-grade backend exploring what it actually takes to serve multiple
isolated tenants from one system: enforced data isolation at the schema
level, per-tenant JWT auth with role-based access control, a background
ingestion pipeline, and (in progress) retrieval with measured, not assumed,
search quality.

Developed and tested on macOS (Apple Silicon) with Python 3.13.

## Setup (zsh, macOS)

```zsh
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies. sentence-transformers pulls in PyTorch, so this
#    is a large install; the embedding model (~90MB) downloads on first use.
pip install fastapi "uvicorn[standard]" "sqlalchemy>=2.0" asyncpg alembic \
  pydantic "pydantic[email]" pydantic-settings "python-jose[cryptography]" \
  bcrypt python-multipart greenlet pgvector sentence-transformers arq

# 3. Postgres 17 + pgvector, and Redis — built and tested against local
#    Homebrew installs. (Not Postgres 14: Homebrew's pgvector only supports
#    17 and 18.)
brew install postgresql@17 pgvector redis
brew services start postgresql@17
brew services start redis
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

# 6. Run the API
uvicorn app.main:app --reload

# 7. In a second terminal (venv active), run the background worker
arq app.worker.WorkerSettings
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
| `POST` | `/documents` | admin, editor | Uploads a `.txt`/`.md` file (≤1 MB) and queues indexing; returns 202 |
| `GET` | `/documents` | any role | Lists the tenant's documents with status and chunk count |
| `GET` | `/documents/{id}` | any role | Indexing status for one document |
| `DELETE` | `/documents/{id}` | admin, editor | Deletes a document and its chunks |

Full interactive docs (request/response schemas, try-it-out): `/docs`.

## What's done vs. what's next

| Done | Not yet |
|---|---|
| Async FastAPI app, Alembic migrations against real Postgres | Search endpoint (vector, then hybrid keyword + vector) |
| `Tenant` / `User` models, tenant isolation via `TenantScopedMixin` | Answer generation with cited sources |
| Tenant registration (atomic tenant + admin user creation) | Redis semantic caching |
| JWT auth, login scoped per tenant | Evaluation harness (precision/recall on a labeled query set) |
| RBAC (`require_role`) and tenant-scoped queries, verified across two tenants | Automated tests + CI |
| `documents` / `document_chunks` schema with a `vector(384)` column (pgvector) | React frontend |
| Paragraph-aware text chunker with overlap | |
| Local embedding service (`all-MiniLM-L6-v2`, no API key or cost) | |
| Upload API + `arq` background worker: chunk, embed, store | |
| Incremental re-indexing: edits re-embed only changed chunks | |

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

**Ingestion is asynchronous.** Uploads are saved and queued, then return
immediately (202); a separate `arq` worker chunks, embeds, and stores. The
embedding model loads in the worker, never in the API process. A document's
status moves `pending` → `processing` → `ready` or `failed` (with a reason).

**Re-indexing is incremental.** The original text is stored, and on
re-upload the worker embeds only chunks whose text it hasn't seen. Observed:
a one-line edit to an 11-chunk document re-embedded 1 chunk and reused 10.
Old chunks stay searchable until the new set is swapped in atomically.

**Concurrent uploads are safe.** If a file is re-uploaded while an older job
is still running, the older job notices its content hash is stale and
discards its result instead of overwriting the newer version.

**Failure handling.** If Redis is unavailable, uploads return 503 and the
document is marked `failed`; the API itself and login keep working.
Re-uploading a document that isn't `ready` (failed, or stuck because a
worker died) queues it again. The `arq` worker exits if Redis restarts, so
run it under a process supervisor in production.

**Logging.** In `development`, SQL is echoed to the console, which includes
document text and embedding vectors. Never run production with
`ENVIRONMENT=development`.

**Exact vector search for now.** No approximate index yet, so search has
perfect recall. An index will be added later and its effect on recall and
latency measured.

## Folder layout

```
app/
  core/         — settings, password hashing, JWT, Redis queue connection
  db/           — engine, session, declarative base + mixins
  models/       — SQLAlchemy models (Tenant, User, Document, DocumentChunk)
  schemas/      — Pydantic request/response models
  services/     — chunking, embeddings, ingestion
  api/
    deps.py     — shared dependencies (get_current_user, require_role)
    routes/     — one router per resource (tenants, auth, users, documents)
  worker.py     — arq background worker
migrations/     — Alembic migration scripts
```