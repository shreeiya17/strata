"""
Background worker. Run it in its own terminal (the API process never
imports the embedding model):

    arq app.worker.WorkerSettings
"""
import asyncio
import logging
import uuid

from app.core.queue import get_redis_settings
from app.db.session import engine
from app.services.embeddings import embed_texts
from app.services.ingestion import ingest_document

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    # arq only sets up logging for its own "arq" loggers, so without this the
    # app's INFO messages (e.g. "12 chunks (1 embedded, 11 reused)") vanish.
    app_logger = logging.getLogger("app")
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)


async def startup(ctx) -> None:
    _configure_logging()
    # Load the model now rather than on the first job: a missing or corrupt
    # model fails loudly at boot, and the first upload isn't the slow one.
    await asyncio.to_thread(embed_texts, ["warm up"])
    logger.info("embedding model loaded")


async def shutdown(ctx) -> None:
    await engine.dispose()


async def ingest_document_job(ctx, document_id: str) -> None:
    await ingest_document(uuid.UUID(document_id))


class WorkerSettings:
    functions = [ingest_document_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = get_redis_settings()
    max_jobs = 2  # embedding is CPU-bound; more parallelism just contends
    job_timeout = 600
    # ingest_document records its own failures on the document row, so
    # retries only matter for hard crashes and timeouts.
    max_tries = 3