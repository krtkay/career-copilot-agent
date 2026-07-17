"""Simple, dependency-free recursive text chunker.

Splits on paragraph boundaries first, then packs paragraphs into ~``chunk_size``
character windows with ``overlap`` characters of context carried between windows.
Good enough for FAQ/policy text; swap for a token-aware splitter if you ingest long
technical docs.
"""

from __future__ import annotations


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= chunk_size:
            current = f"{current}\n\n{para}".strip()
        else:
            if current:
                chunks.append(current)
            if len(para) <= chunk_size:
                current = para
            else:
                # Hard-wrap an over-long paragraph.
                for i in range(0, len(para), chunk_size - overlap):
                    chunks.append(para[i : i + chunk_size])
                current = ""
    if current:
        chunks.append(current)

    # Add overlap by prefixing each chunk with the tail of the previous one.
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            tail = chunks[i - 1][-overlap:]
            overlapped.append(f"{tail} {chunks[i]}")
        return overlapped
    return chunks
