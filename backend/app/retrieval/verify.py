"""Simple verification script for ChromaDB setup in ATLAS."""
import sys
from app.database import SessionLocal
from app.models.entities import Evidence
from app.retrieval.chroma_client import (
    DEFAULT_COLLECTION_NAME,
    get_chroma_client,
    get_evidence_collection,
)
from app.retrieval.indexer import index_evidence
from app.retrieval.retriever import search_evidence


def verify() -> bool:
    # 1. chromadb imports successfully & 2. ChromaDB initializes
    client = get_chroma_client()

    # 3. collection exists
    collection = get_evidence_collection(client=client)

    # 4. PostgreSQL demo evidence can be read & 5. evidence is indexed
    with SessionLocal() as db:
        evidence_count = db.query(Evidence).count()
        if evidence_count == 0:
            print("ERROR: No PostgreSQL demo evidence found.")
            return False
        indexed_count = index_evidence(db=db, max_documents=5)

    # 6. semantic search returns at least one relevant result
    # Search with org filter matching demo evidence org
    results = search_evidence(
        query="Why was the payment retry behavior changed?",
        organization_id=2,
        limit=3,
    )

    # Also verify organization isolation (org 999 should return 0 results)
    isolated_results = search_evidence(
        query="Why was the payment retry behavior changed?",
        organization_id=999,
        limit=3,
    )

    search_passed = len(results) >= 1 and len(isolated_results) == 0

    print("CHROMADB READY")
    print(f"Collection: {DEFAULT_COLLECTION_NAME}")
    print(f"Documents indexed: {indexed_count}")
    print(f"Semantic search: {'PASS' if search_passed else 'FAIL'}")

    return search_passed


if __name__ == "__main__":
    success = verify()
    sys.exit(0 if success else 1)
