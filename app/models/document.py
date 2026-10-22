import uuid
from enum import Enum as PyEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin

# all-MiniLM-L6-v2 produces 384-dimensional vectors. If you ever switch
# embedding models, this number AND a migration must change together.
EMBEDDING_DIM = 384


class DocumentStatus(str, PyEnum):
    PENDING = "pending"  # uploaded, waiting for a worker
    PROCESSING = "processing"  # worker is chunking/embedding it
    READY = "ready"  # searchable
    FAILED = "failed"  # see error_message


class Document(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("tenant_id", "filename", name="uq_documents_tenant_id_filename"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # SHA-256 of the file contents. Lets re-uploads of an unchanged file be
    # skipped, and changed files be detected for incremental re-indexing.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class DocumentChunk(Base, TimestampMixin, TenantScopedMixin):
    """
    tenant_id is deliberately repeated here (it's also reachable via
    document_id). Retrieval queries search THIS table, so putting the
    tenant filter directly on it means a vector search never has to join
    through documents to stay isolated — and can't forget to.
    """

    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_id_chunk_index"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)