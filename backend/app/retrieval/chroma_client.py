import os
from pathlib import Path
import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection

DEFAULT_COLLECTION_NAME = "atlas_engineering_evidence"


def get_chroma_persist_dir() -> str:
    """Return local persistent storage path for ChromaDB."""
    configured_dir = os.getenv("CHROMA_DATA_DIR")
    if configured_dir:
        return configured_dir
    # Default to ./chroma_data relative to backend root
    backend_root = Path(__file__).resolve().parent.parent.parent
    return str(backend_root / "chroma_data")


def get_chroma_client(persist_directory: str | None = None) -> ClientAPI:
    """Initialize or return persistent ChromaDB client."""
    path = persist_directory or get_chroma_persist_dir()
    os.makedirs(path, exist_ok=True)
    return chromadb.PersistentClient(path=path)


def get_evidence_collection(
    client: ClientAPI | None = None,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> Collection:
    """Create or retrieve the evidence collection."""
    if client is None:
        client = get_chroma_client()
    return client.get_or_create_collection(name=collection_name)
