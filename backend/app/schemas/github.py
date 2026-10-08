from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class GitHubRepositoryResponse(BaseModel):
    id: int
    full_name: str
    description: str | None
    language: str | None
    default_branch: str
    html_url: str
    updated_at: datetime | None
    private: bool


class GitHubPullRequestResponse(BaseModel):
    number: int
    title: str
    body: str | None
    state: str
    merged: bool
    author: str | None
    author_avatar_url: str | None
    html_url: str
    created_at: datetime | None
    updated_at: datetime | None
    merged_at: datetime | None
    changed_files: int
    commits: int
    additions: int
    deletions: int


class GitHubFileEvidence(BaseModel):
    filename: str
    status: str
    additions: int
    deletions: int
    changes: int
    patch: str | None
    patch_available: bool
    patch_truncated: bool = False
    blob_url: str | None


class GitHubEvidenceResponse(BaseModel):
    repository: GitHubRepositoryResponse
    pull_request: GitHubPullRequestResponse
    files: list[GitHubFileEvidence]
    reviews: list[dict[str, Any]]
    commits: list[dict[str, Any]]
    signals: dict[str, Any]
    ai_context_ready: bool
    ai_context_record_count: int
    jira_status: Literal["not_connected"] = "not_connected"
    incident_status: Literal["not_connected"] = "not_connected"
    source_note: str = "All fields are returned by GitHub for this request; missing fields remain unavailable."


class AITraceStage(BaseModel):
    id: str
    label: str
    status: Literal["complete", "skipped"]
    detail: str


class GitHubAnalysisResponse(BaseModel):
    knowledge_gap_id: str
    persisted: bool
    provider: str
    model: str
    task: str
    input_record_count: int
    evidence_ids: list[str] = Field(min_length=1)
    signals: dict[str, Any]
    analysis: dict[str, Any]
    stages: list[AITraceStage]
