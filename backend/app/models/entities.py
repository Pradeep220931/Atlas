from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ==============================================================================
# CORE TENANT / ORGANIZATION
# ==============================================================================

class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    teams: Mapped[list["Team"]] = relationship(back_populates="organization")
    services: Mapped[list["Service"]] = relationship(back_populates="organization")
    repositories: Mapped[list["Repository"]] = relationship(back_populates="organization")
    transitions: Mapped[list["Transition"]] = relationship(back_populates="organization")
    integrations: Mapped[list["Integration"]] = relationship(back_populates="organization")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="organization")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="organization")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    organization: Mapped[Organization] = relationship(back_populates="teams")
    users: Mapped[list["User"]] = relationship(back_populates="team")
    members: Mapped[list["TeamMember"]] = relationship(back_populates="team", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(32), index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    organization: Mapped[Organization] = relationship(back_populates="users")
    team: Mapped[Team | None] = relationship(back_populates="users")


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_members_team_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(64), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    team: Mapped[Team] = relationship(back_populates="members")
    user: Mapped[User] = relationship()


# ==============================================================================
# ENGINEERING STRUCTURE
# ==============================================================================

class Service(Base):
    __tablename__ = "services"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_services_org_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    criticality: Mapped[str] = mapped_column(String(32), default="medium")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    organization: Mapped[Organization] = relationship(back_populates="services")
    repositories: Mapped[list["Repository"]] = relationship(back_populates="service")
    knowledge_areas: Mapped[list["KnowledgeArea"]] = relationship(back_populates="service")


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("organization_id", "provider", "external_id", name="uq_repositories_org_provider_ext_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    provider: Mapped[str] = mapped_column(String(32), default="github")
    external_id: Mapped[str] = mapped_column(String(160), index=True)
    html_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    organization: Mapped[Organization] = relationship(back_populates="repositories")
    service: Mapped[Service | None] = relationship(back_populates="repositories")
    pull_requests: Mapped[list["PullRequest"]] = relationship(back_populates="repository")
    commits: Mapped[list["Commit"]] = relationship(back_populates="repository")
    contributors: Mapped[list["RepositoryContributor"]] = relationship(back_populates="repository")


class RepositoryContributor(Base):
    __tablename__ = "repository_contributors"
    __table_args__ = (UniqueConstraint("repository_id", "external_login", name="uq_repo_contributors_repo_login"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    external_login: Mapped[str] = mapped_column(String(160), index=True)
    contributions_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    repository: Mapped[Repository] = relationship(back_populates="contributors")
    user: Mapped[User | None] = relationship()


# ==============================================================================
# SOURCE CONTROL
# ==============================================================================

class PullRequest(Base):
    __tablename__ = "pull_requests"
    __table_args__ = (UniqueConstraint("repository_id", "number", name="uq_pull_requests_repo_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(32), default="open")
    author: Mapped[str | None] = mapped_column(String(160), nullable=True)
    author_avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    html_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    merged: Mapped[bool] = mapped_column(Boolean, default=False)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    changed_files_count: Mapped[int] = mapped_column(Integer, default=0)
    commits_count: Mapped[int] = mapped_column(Integer, default=0)
    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    repository: Mapped[Repository] = relationship(back_populates="pull_requests")
    commits: Mapped[list["Commit"]] = relationship(back_populates="pull_request")
    reviews: Mapped[list["Review"]] = relationship(back_populates="pull_request")
    changed_files: Mapped[list["ChangedFile"]] = relationship(back_populates="pull_request")


class Commit(Base):
    __tablename__ = "commits"
    __table_args__ = (UniqueConstraint("repository_id", "sha", name="uq_commits_repo_sha"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    pull_request_id: Mapped[int | None] = mapped_column(ForeignKey("pull_requests.id", ondelete="SET NULL"), nullable=True, index=True)
    sha: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text)
    author_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    author_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    repository: Mapped[Repository] = relationship(back_populates="commits")
    pull_request: Mapped[PullRequest | None] = relationship(back_populates="commits")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    pull_request_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id", ondelete="CASCADE"), index=True)
    reviewer: Mapped[str] = mapped_column(String(160), index=True)
    state: Mapped[str] = mapped_column(String(32))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pull_request: Mapped[PullRequest] = relationship(back_populates="reviews")


class ChangedFile(Base):
    __tablename__ = "changed_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    pull_request_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(500), index=True)
    status: Mapped[str] = mapped_column(String(32), default="modified")
    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)
    changes: Mapped[int] = mapped_column(Integer, default=0)
    patch: Mapped[str | None] = mapped_column(Text, nullable=True)
    blob_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pull_request: Mapped[PullRequest] = relationship(back_populates="changed_files")


# ==============================================================================
# PROJECT / INCIDENT DATA
# ==============================================================================

class JiraProject(Base):
    __tablename__ = "jira_projects"
    __table_args__ = (UniqueConstraint("organization_id", "key", name="uq_jira_projects_org_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    key: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(160))
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    issues: Mapped[list["JiraIssue"]] = relationship(back_populates="project")


class JiraIssue(Base):
    __tablename__ = "jira_issues"
    __table_args__ = (UniqueConstraint("organization_id", "key", name="uq_jira_issues_org_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    jira_project_id: Mapped[int | None] = mapped_column(ForeignKey("jira_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    summary: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="Open")
    issue_type: Mapped[str] = mapped_column(String(64), default="Task")
    priority: Mapped[str] = mapped_column(String(32), default="Medium")
    assignee: Mapped[str | None] = mapped_column(String(160), nullable=True)
    reporter: Mapped[str | None] = mapped_column(String(160), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project: Mapped[JiraProject | None] = relationship(back_populates="issues")
    comments: Mapped[list["JiraComment"]] = relationship(back_populates="issue")


class JiraComment(Base):
    __tablename__ = "jira_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    jira_issue_id: Mapped[int] = mapped_column(ForeignKey("jira_issues.id", ondelete="CASCADE"), index=True)
    author: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    issue: Mapped[JiraIssue] = relationship(back_populates="comments")


# ==============================================================================
# KNOWLEDGE
# ==============================================================================

class KnowledgeArea(Base):
    __tablename__ = "knowledge_areas"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), default="needs_review")
    criticality: Mapped[str] = mapped_column(String(32), default="medium")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    service: Mapped[Service] = relationship(back_populates="knowledge_areas")


class KnowledgeGap(Base):
    __tablename__ = "knowledge_gaps"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), index=True)
    knowledge_area_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_areas.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(32), default="medium")
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detection_source: Mapped[str] = mapped_column(String(64), default="manual")
    targeted_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_holder_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    validated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    evidence: Mapped[list["Evidence"]] = relationship(back_populates="knowledge_gap")
    records: Mapped[list["KnowledgeRecord"]] = relationship(back_populates="knowledge_gap")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    knowledge_gap_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_gaps.id"), nullable=True, index=True)
    repository_id: Mapped[int | None] = mapped_column(ForeignKey("repositories.id"), nullable=True, index=True)
    pull_request_id: Mapped[int | None] = mapped_column(ForeignKey("pull_requests.id"), nullable=True, index=True)
    jira_issue_id: Mapped[int | None] = mapped_column(ForeignKey("jira_issues.id"), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[str] = mapped_column(String(160), index=True)
    source_url: Mapped[str] = mapped_column(String(500), default="")
    title: Mapped[str] = mapped_column(String(240))
    reference: Mapped[str] = mapped_column(String(500), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(160), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    knowledge_gap: Mapped[KnowledgeGap | None] = relationship(back_populates="evidence")


class KnowledgeRecord(Base):
    __tablename__ = "knowledge_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    knowledge_gap_id: Mapped[int] = mapped_column(ForeignKey("knowledge_gaps.id"), index=True)
    knowledge_area_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_areas.id"), nullable=True, index=True)
    decision: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    affected_system: Mapped[str] = mapped_column(String(160))
    related_incident: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="proposed")
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    validated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    knowledge_gap: Mapped[KnowledgeGap] = relationship(back_populates="records")


# ==============================================================================
# KNOWLEDGE TRANSFER
# ==============================================================================

class Transition(Base):
    __tablename__ = "transitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), index=True)
    outgoing_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    incoming_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    target_completion_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="transitions")
    areas: Mapped[list["TransitionKnowledgeArea"]] = relationship(back_populates="transition", cascade="all, delete-orphan")
    checks: Mapped[list["KnowledgeCheck"]] = relationship(back_populates="transition", cascade="all, delete-orphan")


class TransitionKnowledgeArea(Base):
    __tablename__ = "transition_knowledge_areas"

    id: Mapped[int] = mapped_column(primary_key=True)
    transition_id: Mapped[int] = mapped_column(ForeignKey("transitions.id"), index=True)
    knowledge_area_id: Mapped[int] = mapped_column(ForeignKey("knowledge_areas.id"))
    status: Mapped[str] = mapped_column(String(32), default="needs_review")
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    transition: Mapped[Transition] = relationship(back_populates="areas")


class KnowledgeCheck(Base):
    __tablename__ = "knowledge_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    transition_id: Mapped[int] = mapped_column(ForeignKey("transitions.id", ondelete="CASCADE"), index=True)
    knowledge_area_id: Mapped[int] = mapped_column(ForeignKey("knowledge_areas.id"), index=True)
    knowledge_record_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_records.id", ondelete="SET NULL"), nullable=True)
    question: Mapped[str] = mapped_column(Text)
    expected_knowledge: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    transition: Mapped[Transition] = relationship(back_populates="checks")
    attempts: Mapped[list["KnowledgeCheckAttempt"]] = relationship(back_populates="check", cascade="all, delete-orphan")


class KnowledgeCheckAttempt(Base):
    __tablename__ = "knowledge_check_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_check_id: Mapped[int] = mapped_column(ForeignKey("knowledge_checks.id", ondelete="CASCADE"), index=True)
    incoming_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    answer: Mapped[str] = mapped_column(Text)
    evaluation_result: Mapped[str] = mapped_column(String(32), default="pending")
    evaluator_type: Mapped[str] = mapped_column(String(32), default="human")
    evaluator_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    feedback: Mapped[str] = mapped_column(Text, default="")
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    check: Mapped[KnowledgeCheck] = relationship(back_populates="attempts")


# ==============================================================================
# INTEGRATIONS
# ==============================================================================

class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("organization_id", "provider", name="uq_integrations_org_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="not_configured")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    organization: Mapped[Organization] = relationship(back_populates="integrations")
    sync_runs: Mapped[list["IntegrationSyncRun"]] = relationship(back_populates="integration", cascade="all, delete-orphan")


class IntegrationSyncRun(Base):
    __tablename__ = "integration_sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    integration_id: Mapped[int] = mapped_column(ForeignKey("integrations.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    items_synced: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    integration: Mapped[Integration] = relationship(back_populates="sync_runs")


# ==============================================================================
# SECURITY & GOVERNANCE
# ==============================================================================

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(160), index=True)
    resource_type: Mapped[str] = mapped_column(String(64), index=True)
    resource_id: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), default="success")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    organization: Mapped[Organization] = relationship(back_populates="audit_logs")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    message: Mapped[str] = mapped_column(Text)
    action_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    organization: Mapped[Organization] = relationship(back_populates="notifications")