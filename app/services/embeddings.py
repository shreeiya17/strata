from functools import lru_cache

from app.models.document import EMBEDDING_DIM

MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model():
    # Imported inside the function on purpose: sentence_transformers pulls in
    # PyTorch, which takes seconds to import. The web API process should not
    # pay that cost (or hold the model in memory) unless it actually embeds
    # something. lru_cache means the model loads once per process.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Returns one EMBEDDING_DIM-length vector per input text, L2-normalised so
    cosine similarity and dot product agree.

    This is synchronous, CPU-bound work. Don't call it from an async route
    handler — it would block the event loop for every other request. It's
    meant to run in the background worker.
    """
    if not texts:
        return []

    vectors = _get_model().encode(
        texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False
    ).tolist()

    # Guard against a model swap that forgot the DB column: fail loudly here
    # instead of with a confusing Postgres dimension error on insert.
    if len(vectors[0]) != EMBEDDING_DIM:
        raise RuntimeError(
            f"{MODEL_NAME} produced {len(vectors[0])}-dim vectors but the "
            f"database column expects {EMBEDDING_DIM}"
        )
    return vectors