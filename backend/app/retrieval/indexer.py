import logging
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.entities import Commit, Evidence, JiraIssue, PullRequest
from app.retrieval.chroma_client import get_evidence_collection

logger = logging.getLogger(__name__)


def build_evidence_document_text(
    evidence: Evidence,
    pull_request: PullRequest | None = None,
    jira_issue: JiraIssue | None = None,
    commit: Commit | None = None,
) -> str:
    """Build rich semantic text representation from evidence and related entities."""
    parts: list[str] = []

    # Primary statement / summary / content
    if evidence.summary:
        parts.append(evidence.summary)
    elif evidence.content:
        parts.append(evidence.content)

    if evidence.title and evidence.title not in parts:
        parts.append(f"Title: {evidence.title}")

    if evidence.reference:
        parts.append(f"Reference: {evidence.reference}")

    # Related Pull Request context
    if pull_request:
        parts.append(f"Pull Request #{pull_request.number}: {pull_request.title}")
        if pull_request.body:
            parts.append(f"PR Summary: {pull_request.body}")

    # Related Jira Issue context
    if jira_issue:
        parts.append(f"Jira {jira_issue.key}: {jira_issue.summary}")
        if jira_issue.description:
            parts.append(f"Issue Context: {jira_issue.description}")

    # Related Commit context
    if commit and commit.message:
        parts.append(f"Commit: {commit.message}")

    return "\n".join(p.strip() for p in parts if p and p.strip())


def index_evidence(
    db: Session,
    collection_name: str | None = None,
    max_documents: int = 5,
) -> int:
    """Read evidence records from PostgreSQL and upsert them into ChromaDB.
    
    Returns the number of documents indexed.
    """
    collection = get_evidence_collection(collection_name=collection_name) if collection_name else get_evidence_collection()

    evidence_query = select(Evidence).order_by(Evidence.id.asc()).limit(max_documents)
    evidence_records = list(db.scalars(evidence_query).all())

    if not evidence_records:
        logger.info("No evidence records found in PostgreSQL to index.")
        return 0

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for ev in evidence_records:
        # Resolve related entities if available
        pr: PullRequest | None = None
        if ev.pull_request_id:
            pr = db.get(PullRequest, ev.pull_request_id)

        jira: JiraIssue | None = None
        if ev.jira_issue_id:
            jira = db.get(JiraIssue, ev.jira_issue_id)

        commit: Commit | None = None
        commit_sha: str | None = None
        if isinstance(ev.metadata_json, dict):
            commit_sha = ev.metadata_json.get("commit_sha")
        if commit_sha and ev.repository_id:
            commit = db.scalar(
                select(Commit).where(
                    Commit.repository_id == ev.repository_id,
                    Commit.sha == commit_sha,
                )
            )

        doc_text = build_evidence_document_text(ev, pull_request=pr, jira_issue=jira, commit=commit)

        # Build metadata (ChromaDB allows strings, ints, floats, bools)
        metadata: dict[str, Any] = {
            "organization_id": int(ev.organization_id) if ev.organization_id is not None else 0,
            "source_type": str(ev.source_type or ""),
            "source_id": str(ev.source_id or ""),
        }
        if ev.repository_id is not None:
            metadata["repository_id"] = int(ev.repository_id)
        if ev.jira_issue_id is not None:
            metadata["jira_issue_id"] = int(ev.jira_issue_id)
        if commit_sha:
            metadata["commit_id"] = str(commit_sha)

        doc_id = f"evidence-{ev.id}"

        ids.append(doc_id)
        documents.append(doc_text)
        metadatas.append(metadata)

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    logger.info(f"Successfully indexed {len(ids)} evidence documents into ChromaDB.")
    return len(ids)
