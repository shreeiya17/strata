import hashlib
import logging
import uuid
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.queue import get_queue
from app.db.session import get_db
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.models.tenant import User, UserRole
from app.schemas.document import DocumentRead

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_UPLOAD_BYTES = 1_000_000
ALLOWED_EXTENSIONS = {".txt", ".md", ".markdown"}


def _with_chunk_counts():
    return (
        select(Document, func.count(DocumentChunk.id).label("chunk_count"))
        .outerjoin(DocumentChunk, DocumentChunk.document_id == Document.id)
        .group_by(Document.id)
    )


def _to_read(doc: Document, chunk_count: int) -> DocumentRead:
    return DocumentRead(
        id=doc.id,
        filename=doc.filename,
        status=doc.status,
        error_message=doc.error_message,
        chunk_count=chunk_count,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


async def _read_one(db: AsyncSession, document_id: uuid.UUID, tenant_id: uuid.UUID) -> DocumentRead | None:
    row = (
        await db.execute(
            _with_chunk_counts().where(Document.id == document_id, Document.tenant_id == tenant_id)
        )
    ).first()
    return _to_read(row[0], row[1]) if row else None


@router.post("", response_model=DocumentRead, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    response: Response,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.EDITOR)),
) -> DocumentRead:
    """
    Saves the file and queues it for indexing — returns 202 immediately; poll
    GET /documents/{id} for status. Re-uploading a filename replaces that
    document; identical content that is already indexed is detected by hash and skipped.
    """
    name = PurePosixPath(file.filename or "").name  # drop any client-supplied directories
    if not name or len(name) > 255:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing or invalid filename")
    if PurePosixPath(name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Only {', '.join(sorted(ALLOWED_EXTENSIONS))} files are supported",
        )

    data = await file.read(MAX_UPLOAD_BYTES + 1)  # +1 so we can tell "too big" from "exactly the limit"
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File exceeds {MAX_UPLOAD_BYTES} bytes")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File is not valid UTF-8 text")
    # Postgres text columns cannot hold NUL bytes — a binary file renamed to
    # .txt would otherwise surface as a 500 from the database.
    if "\x00" in text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File appears to be binary, not text")
    if not text.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File is empty")

    content_hash = hashlib.sha256(data).hexdigest()
    tenant_id = current_user.tenant_id

    existing = (
        await db.execute(
            select(Document).where(Document.tenant_id == tenant_id, Document.filename == name)
        )
    ).scalar_one_or_none()

    if existing is not None and existing.content_hash == content_hash and existing.status == DocumentStatus.READY:
        # Already indexed and unchanged — nothing to do. Anything that ISN'T
        # ready (failed, or stuck pending/processing because a worker died or
        # a queued job was lost) falls through and is queued again, so
        # re-uploading is always a way to retry.
        response.status_code = status.HTTP_200_OK
        return await _read_one(db, existing.id, tenant_id)

    if existing is not None:
        doc = existing
        doc.content = text
        doc.content_hash = content_hash
        doc.status = DocumentStatus.PENDING
        doc.error_message = None
        doc.uploaded_by_id = current_user.id
    else:
        doc = Document(
            tenant_id=tenant_id,
            uploaded_by_id=current_user.id,
            filename=name,
            content=text,
            content_hash=content_hash,
        )
        db.add(doc)

    try:
        await db.commit()
    except IntegrityError:
        # Two simultaneous uploads of the same new filename raced; the loser lands here.
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A document with this filename is already being created")

    try:
        queue = await get_queue()
        await queue.enqueue_job("ingest_document_job", str(doc.id))
    except Exception:
        logger.exception("could not enqueue ingestion for %s", doc.id)
        doc.status = DocumentStatus.FAILED
        doc.error_message = "Could not queue indexing job"
        await db.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Indexing queue unavailable. The file was saved but not indexed; upload it again to retry.",
        )

    return await _read_one(db, doc.id, tenant_id)


@router.get("", response_model=list[DocumentRead])
async def list_documents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DocumentRead]:
    rows = await db.execute(
        _with_chunk_counts().where(Document.tenant_id == current_user.tenant_id).order_by(Document.created_at)
    )
    return [_to_read(doc, count) for doc, count in rows.all()]


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentRead:
    result = await _read_one(db, document_id, current_user.tenant_id)
    if result is None:
        # Same 404 whether it doesn't exist or belongs to another tenant, so
        # ids can't be probed to discover other tenants' documents.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return result


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN, UserRole.EDITOR)),
) -> None:
    doc = (
        await db.execute(
            select(Document).where(Document.id == document_id, Document.tenant_id == current_user.tenant_id)
        )
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    await db.delete(doc)  # chunks go with it via ON DELETE CASCADE
    await db.commit()