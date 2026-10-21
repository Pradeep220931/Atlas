import logging
from typing import Any
from app.retrieval.chroma_client import get_evidence_collection

logger = logging.getLogger(__name__)


def search_evidence(
    query: str,
    organization_id: int | None = None,
    limit: int = 3,
    collection_name: str | None = None,
) -> list[dict[str, Any]]:
    """Perform semantic search against ChromaDB engineering evidence.
    
    Filters by organization_id to enforce multi-tenant isolation.
    """
    collection = get_evidence_collection(collection_name=collection_name) if collection_name else get_evidence_collection()

    count = collection.count()
    if count == 0:
        return []

    # Limit search results to maximum of 3 for the demo
    n_results = min(max(1, limit), min(count, 3))

    query_kwargs: dict[str, Any] = {
        "query_texts": [query],
        "n_results": n_results,
    }

    if organization_id is not None:
        query_kwargs["where"] = {"organization_id": int(organization_id)}

    try:
        results = collection.query(**query_kwargs)
    except Exception as e:
        logger.error(f"Error querying ChromaDB: {e}")
        return []

    output: list[dict[str, Any]] = []
    documents = results.get("documents", [[]])[0] if results.get("documents") else []
    metadatas = results.get("metadatas", [[]])[0] if results.get("metadatas") else []
    ids = results.get("ids", [[]])[0] if results.get("ids") else []
    distances = results.get("distances", [[]])[0] if results.get("distances") else []

    for idx, doc in enumerate(documents):
        meta = metadatas[idx] if idx < len(metadatas) and metadatas[idx] is not None else {}
        source_type = meta.get("source_type", "")
        source_id = meta.get("source_id", "")
        item: dict[str, Any] = {
            "id": ids[idx] if idx < len(ids) else f"result-{idx}",
            "text": doc,
            "source_type": source_type,
            "source_id": source_id,
            "metadata": meta,
        }
        if idx < len(distances):
            item["distance"] = distances[idx]
        output.append(item)

    return output
