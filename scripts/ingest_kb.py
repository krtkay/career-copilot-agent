"""Ingest the knowledge base into Postgres (chunks + embeddings + tsvector).

Run:  python -m scripts.ingest_kb  [--reset]

For each markdown file in ``data/knowledge_base``:
  * the H1 title becomes the document title
  * the body is chunked (see app.utils.chunking)
  * each chunk is embedded locally with fastembed
  * chunks are written to ``kb_chunks`` (the ``content_tsv`` keyword column is
    computed by Postgres automatically)
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from sqlalchemy import text

from app.core.logging import configure_logging, get_logger
from app.models.kb import KBChunk, KBDocument
from app.services.database import AsyncSessionLocal, engine, init_db
from app.services.embeddings import embedding_service
from app.utils.chunking import chunk_text

configure_logging()
logger = get_logger(__name__)

KB_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge_base"


def _title_and_body(md: str, fallback: str) -> tuple[str, str]:
    lines = md.splitlines()
    title = fallback
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("# "):
            title = line[2:].strip()
            body_start = i + 1
            break
    return title, "\n".join(lines[body_start:]).strip()


async def _reset() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE kb_chunks, kb_documents CASCADE"))
    logger.info("kb_reset")


async def ingest() -> None:
    await init_db()
    files = sorted(KB_DIR.glob("*.md"))
    if not files:
        logger.warning("no_kb_files", dir=str(KB_DIR))
        return

    total_chunks = 0
    async with AsyncSessionLocal() as session:
        for path in files:
            raw = path.read_text(encoding="utf-8")
            title, body = _title_and_body(raw, path.stem)
            category = path.stem
            doc = KBDocument(title=title, source=path.name, category=category)
            session.add(doc)
            await session.flush()  # get doc.id

            chunks = chunk_text(body)
            vectors = embedding_service.embed_documents(chunks)
            for idx, (content, vec) in enumerate(zip(chunks, vectors, strict=True)):
                session.add(
                    KBChunk(
                        document_id=doc.id,
                        chunk_index=idx,
                        content=content,
                        embedding=vec,
                    )
                )
            total_chunks += len(chunks)
            logger.info("ingested_document", title=title, chunks=len(chunks))
        await session.commit()
    logger.info("ingest_complete", documents=len(files), chunks=total_chunks)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Truncate KB first.")
    args = parser.parse_args()
    if args.reset:
        await init_db()
        await _reset()
    await ingest()


if __name__ == "__main__":
    asyncio.run(main())
