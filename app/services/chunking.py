"""
Splits a document into overlapping chunks small enough to embed.

Why the defaults: all-MiniLM-L6-v2 silently truncates anything beyond ~256
word-pieces (roughly 1000 characters of prose, fewer for code-heavy text).
A chunk longer than that is partly invisible to search, so max_chars stays
comfortably under it. Overlap keeps a sentence that straddles a boundary
retrievable from either side. Both are tuning knobs to revisit once the
evaluation harness exists — chunk size is one of the ablations planned.
"""

# Tried in order: prefer breaking at a paragraph, then a line, then a
# sentence, then a word. Only fall back to a harder cut when needed.
_SEPARATORS = ["\n\n", "\n", ". ", " "]


def chunk_text(text: str, max_chars: int = 800, overlap: int = 150) -> list[str]:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap < 0 or overlap >= max_chars:
        raise ValueError("overlap must be >= 0 and smaller than max_chars")

    text = text.strip()
    if not text:
        return []

    pieces = _split_to_pieces(text, max_chars, _SEPARATORS)
    return _pack_with_overlap(pieces, max_chars, overlap)


def _split_to_pieces(text: str, max_chars: int, separators: list[str]) -> list[str]:
    """Recursively break text into pieces that are each <= max_chars."""
    if len(text) <= max_chars:
        return [text]

    if not separators:
        # No natural break left (e.g. one enormous token): hard cut.
        return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]

    sep, rest = separators[0], separators[1:]
    parts = text.split(sep)
    pieces: list[str] = []
    for i, part in enumerate(parts):
        # Re-attach the separator so no text is lost or glued together.
        part = part + sep if i < len(parts) - 1 else part
        if not part.strip():
            continue
        pieces.extend(_split_to_pieces(part, max_chars, rest))
    return pieces


def _pack_with_overlap(pieces: list[str], max_chars: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + len(piece) > max_chars:
            chunks.append(current.strip())
            # Start the next chunk with the tail of this one, cut at a word
            # boundary so we don't begin mid-word.
            tail = current[-overlap:] if overlap else ""
            if tail and " " in tail:
                tail = tail[tail.index(" ") + 1 :]
            current = tail
            # The overlap tail plus this piece can still exceed the cap.
            if len(current) + len(piece) > max_chars:
                current = ""
        current += piece
    if current.strip():
        chunks.append(current.strip())
    return chunks