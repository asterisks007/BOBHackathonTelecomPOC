"""
Data ingestion script — loads synthetic seed data into ChromaDB.

Run once before first use:
    cd bobCode
    python data/ingest.py

Safe to re-run — uses upsert (existing documents are overwritten, not duplicated).
This script reads ONLY from data/seed_data/ — no external data sources.
"""

import json
import logging
import sys
from pathlib import Path

# Ensure bobCode/ is on the Python path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.vectorstore import VectorStore

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "seed_data"


def ingest_incidents(store: VectorStore) -> int:
    """Ingest historical incident records into the knowledge base collection."""
    incidents_file = DATA_DIR / "incidents.json"
    with open(incidents_file, encoding="utf-8") as f:
        incidents = json.load(f)

    documents = []
    ids = []
    metadatas = []

    for inc in incidents:
        # Build a rich text blob combining description + root_cause + resolution
        # for semantic similarity search
        doc_text = (
            f"Incident type: {inc['type']}. "
            f"Service: {inc['service']}. "
            f"Location: {inc['location']}. "
            f"Description: {inc['description']} "
            f"Root cause: {inc['root_cause']} "
            f"Resolution: {inc['resolution']}"
        )
        documents.append(doc_text)
        ids.append(inc["id"])
        metadatas.append(
            {
                "type": inc["type"],
                "service": inc["service"],
                "severity": inc["severity"],
                "mttr_minutes": inc["mttr_minutes"],
                "affected_customers": inc["affected_customers"],
            }
        )

    count = store.ingest(documents, ids, metadatas)
    logger.info("Ingested %d incidents into telecom_knowledge_base", count)
    return count


def ingest_knowledge_base(store: VectorStore) -> int:
    """Ingest resolution patterns from the knowledge base text file."""
    kb_file = DATA_DIR / "knowledge_base.txt"
    text = kb_file.read_text(encoding="utf-8")

    # Split by section (double newlines after SECTION header)
    chunks = []
    current_chunk: list = []
    for line in text.splitlines():
        if line.startswith("PATTERN:") and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
        else:
            current_chunk.append(line)
    if current_chunk:
        chunks.append("\n".join(current_chunk))

    # Filter out empty chunks and header lines
    chunks = [c.strip() for c in chunks if len(c.strip()) > 50]

    documents = chunks
    ids = [f"KB-{i:04d}" for i in range(len(chunks))]
    metadatas = [{"source": "knowledge_base.txt", "chunk_index": i} for i in range(len(chunks))]

    count = store.ingest(documents, ids, metadatas)
    logger.info("Ingested %d knowledge base chunks", count)
    return count


def main() -> None:
    """Run full ingestion pipeline."""
    logger.info("Starting data ingestion into ChromaDB...")
    store = VectorStore()

    total = 0
    total += ingest_incidents(store)
    total += ingest_knowledge_base(store)

    logger.info("Ingestion complete. Total documents: %d | Collection size: %d", total, store.count())


if __name__ == "__main__":
    main()
