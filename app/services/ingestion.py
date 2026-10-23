import asyncio
import logging
import uuid
from collections.abc import Callable

from sqlalchemy import delete, select, update

from app.db.session import AsyncSessionLocal
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.services.chunking import chunk_text
from app.services.embeddings import embed_texts

logger = logging.getLogger(__name__)


async def ingest_document(
    document_id: uuid.UUID,
    *,
    session_factory=AsyncSessionLocal,
    embed: Callable[[list[str]], list[list[float]]] = embed_texts,
    chunk: Callable[[str], list[str]] = chunk_text,
) -> None:
    """
    Turns a Document's text into searchable chunks. Safe to run more than
    once for the same document (re-uploads, retries).

    The embed/chunk/session_factory parameters exist so tests can swap in
    fakes; production callers just pass document_id.
    """
    # Step 1 — claim the document and snapshot what we're about to process.
    async with session_factory() as db:
        doc = await db.get(Document, document_id)
        if doc is None:
            return  # deleted before the worker got to it
        text, started_hash, tenant_id = doc.content, doc.content_hash, doc.tenant_id
        doc.status = DocumentStatus.PROCESSING
        doc.error_message = None
        await db.commit()

        # Embeddings we already have for this document, keyed by chunk text.
        rows = await db.execute(
            select(DocumentChunk.content, DocumentChunk.embedding).where(
                DocumentChunk.document_id == document_id
            )
        )
        existing = {content: embedding for content, embedding in rows.all()}

    try:
        chunks = chunk(text)
        if not chunks:
            raise ValueError("Document contains no text to index")

        # Step 2 — embed ONLY chunks whose text we haven't embedded before.
        # On a first ingest that's all of them; after a small edit it's just
        # the chunks around the edit. Embedding is the expensive step.
        to_embed = list(dict.fromkeys(c for c in chunks if c not in existing))
        new_vectors = await asyncio.to_thread(embed, to_embed) if to_embed else []
        vectors = {**existing, **dict(zip(to_embed, new_vectors))}

        # Step 3 — write atomically, but only if we're still the current
        # version. The row lock serialises concurrent jobs for one document.
        async with session_factory() as db:
            result = await db.execute(
                select(Document).where(Document.id == document_id).with_for_update()
            )
            doc = result.scalar_one_or_none()
            if doc is None or doc.content_hash != started_hash:
                # Deleted, or a newer upload changed the content while we
                # were embedding. That upload enqueued its own job; drop ours.
                logger.info("ingest %s: superseded or deleted, discarding result", document_id)
                return

            await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
            db.add_all(
                DocumentChunk(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    chunk_index=i,
                    content=c,
                    embedding=vectors[c],
                )
                for i, c in enumerate(chunks)
            )
            doc.status = DocumentStatus.READY
            await db.commit()

        logger.info(
            "ingest %s: %d chunks (%d embedded, %d reused)",
            document_id, len(chunks), len(to_embed), len(chunks) - len(to_embed),
        )

    except Exception as exc:
        logger.exception("ingest %s failed", document_id)
        async with session_factory() as db:
            # Only mark failure if this is still the current version.
            await db.execute(
                update(Document)
                .where(Document.id == document_id, Document.content_hash == started_hash)
                .values(status=DocumentStatus.FAILED, error_message=str(exc)[:500])
            )
            await db.commit()