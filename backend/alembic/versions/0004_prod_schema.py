"""Production relational schema for ATLAS continuity platform.

Revision ID: 0004_prod_schema
Revises: 0003_knowledge_gap_ai_analysis
Create Date: 2026-10-08
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_prod_schema"
down_revision = "0003_knowledge_gap_ai_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # --------------------------------------------------------------------------
    # 1. Update existing tables if needed
    # --------------------------------------------------------------------------

    # teams
    if "teams" in existing_tables:
        team_cols = {c["name"] for c in inspector.get_columns("teams")}
        with op.batch_alter_table("teams") as batch:
            if "description" not in team_cols:
                batch.add_column(sa.Column("description", sa.Text(), nullable=True, server_default=""))
            if "created_at" not in team_cols:
                batch.add_column(sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))
            if "updated_at" not in team_cols:
                batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))

    # users
    if "users" in existing_tables:
        user_cols = {c["name"] for c in inspector.get_columns("users")}
        with op.batch_alter_table("users") as batch:
            if "updated_at" not in user_cols:
                batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))

    # services
    if "services" in existing_tables:
        svc_cols = {c["name"] for c in inspector.get_columns("services")}
        with op.batch_alter_table("services") as batch:
            if "created_at" not in svc_cols:
                batch.add_column(sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))
            if "updated_at" not in svc_cols:
                batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))

    # repositories
    if "repositories" in existing_tables:
        repo_cols = {c["name"] for c in inspector.get_columns("repositories")}
        with op.batch_alter_table("repositories") as batch:
            if "html_url" not in repo_cols:
                batch.add_column(sa.Column("html_url", sa.String(500), nullable=True))
            if "default_branch" not in repo_cols:
                batch.add_column(sa.Column("default_branch", sa.String(100), server_default="main", nullable=True))
            if "created_at" not in repo_cols:
                batch.add_column(sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))
            if "updated_at" not in repo_cols:
                batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))

    # knowledge_areas
    if "knowledge_areas" in existing_tables:
        ka_cols = {c["name"] for c in inspector.get_columns("knowledge_areas")}
        with op.batch_alter_table("knowledge_areas") as batch:
            if "organization_id" not in ka_cols:
                batch.add_column(sa.Column("organization_id", sa.Integer(), nullable=True))
                batch.create_foreign_key("fk_knowledge_areas_org", "organizations", ["organization_id"], ["id"])
            if "created_at" not in ka_cols:
                batch.add_column(sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))
            if "updated_at" not in ka_cols:
                batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))

    # knowledge_gaps
    if "knowledge_gaps" in existing_tables:
        kg_cols = {c["name"] for c in inspector.get_columns("knowledge_gaps")}
        with op.batch_alter_table("knowledge_gaps") as batch:
            if "organization_id" not in kg_cols:
                batch.add_column(sa.Column("organization_id", sa.Integer(), nullable=True))
                batch.create_foreign_key("fk_knowledge_gaps_org", "organizations", ["organization_id"], ["id"])
            if "assigned_holder_id" not in kg_cols:
                batch.add_column(sa.Column("assigned_holder_id", sa.Integer(), nullable=True))
                batch.create_foreign_key("fk_knowledge_gaps_assigned_holder", "users", ["assigned_holder_id"], ["id"])
            if "reviewer_id" not in kg_cols:
                batch.add_column(sa.Column("reviewer_id", sa.Integer(), nullable=True))
                batch.create_foreign_key("fk_knowledge_gaps_reviewer", "users", ["reviewer_id"], ["id"])
            if "validated_by" not in kg_cols:
                batch.add_column(sa.Column("validated_by", sa.Integer(), nullable=True))
                batch.create_foreign_key("fk_knowledge_gaps_validated_by", "users", ["validated_by"], ["id"])
            if "validated_at" not in kg_cols:
                batch.add_column(sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True))
            if "confidence" not in kg_cols:
                batch.add_column(sa.Column("confidence", sa.Integer(), nullable=True))
            if "detection_source" not in kg_cols:
                batch.add_column(sa.Column("detection_source", sa.String(64), server_default="manual", nullable=True))
            if "targeted_question" not in kg_cols:
                batch.add_column(sa.Column("targeted_question", sa.Text(), nullable=True))

    # evidence
    if "evidence" in existing_tables:
        ev_cols = {c["name"] for c in inspector.get_columns("evidence")}
        with op.batch_alter_table("evidence") as batch:
            if "organization_id" not in ev_cols:
                batch.add_column(sa.Column("organization_id", sa.Integer(), nullable=True))
                batch.create_foreign_key("fk_evidence_org", "organizations", ["organization_id"], ["id"])
            if "repository_id" not in ev_cols:
                batch.add_column(sa.Column("repository_id", sa.Integer(), nullable=True))
                batch.create_foreign_key("fk_evidence_repo", "repositories", ["repository_id"], ["id"])
            if "pull_request_id" not in ev_cols:
                batch.add_column(sa.Column("pull_request_id", sa.Integer(), nullable=True))
            if "jira_issue_id" not in ev_cols:
                batch.add_column(sa.Column("jira_issue_id", sa.Integer(), nullable=True))
            if "source_url" not in ev_cols:
                batch.add_column(sa.Column("source_url", sa.String(500), server_default="", nullable=True))
            if "content" not in ev_cols:
                batch.add_column(sa.Column("content", sa.Text(), nullable=True))
            if "author" not in ev_cols:
                batch.add_column(sa.Column("author", sa.String(160), nullable=True))
            if "metadata_json" not in ev_cols:
                batch.add_column(sa.Column("metadata_json", sa.JSON(), nullable=True))
            if "created_at" not in ev_cols:
                batch.add_column(sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))
            if "updated_at" not in ev_cols:
                batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))

    # knowledge_records
    if "knowledge_records" in existing_tables:
        kr_cols = {c["name"] for c in inspector.get_columns("knowledge_records")}
        with op.batch_alter_table("knowledge_records") as batch:
            if "organization_id" not in kr_cols:
                batch.add_column(sa.Column("organization_id", sa.Integer(), nullable=True))
                batch.create_foreign_key("fk_knowledge_records_org", "organizations", ["organization_id"], ["id"])
            if "updated_at" not in kr_cols:
                batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))

    # transitions
    if "transitions" in existing_tables:
        tr_cols = {c["name"] for c in inspector.get_columns("transitions")}
        with op.batch_alter_table("transitions") as batch:
            if "manager_id" not in tr_cols:
                batch.add_column(sa.Column("manager_id", sa.Integer(), nullable=True))
                batch.create_foreign_key("fk_transitions_manager", "users", ["manager_id"], ["id"])
            if "start_date" not in tr_cols:
                batch.add_column(sa.Column("start_date", sa.DateTime(timezone=True), nullable=True))
            if "target_completion_date" not in tr_cols:
                batch.add_column(sa.Column("target_completion_date", sa.DateTime(timezone=True), nullable=True))

    # integrations
    if "integrations" in existing_tables:
        it_cols = {c["name"] for c in inspector.get_columns("integrations")}
        with op.batch_alter_table("integrations") as batch:
            if "created_at" not in it_cols:
                batch.add_column(sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))
            if "updated_at" not in it_cols:
                batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))

    # --------------------------------------------------------------------------
    # 2. Create new tables
    # --------------------------------------------------------------------------

    # team_members
    if "team_members" not in existing_tables:
        op.create_table(
            "team_members",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("role", sa.String(64), server_default="member", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("team_id", "user_id", name="uq_team_members_team_user"),
        )

    # repository_contributors
    if "repository_contributors" not in existing_tables:
        op.create_table(
            "repository_contributors",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("external_login", sa.String(160), nullable=False, index=True),
            sa.Column("contributions_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("repository_id", "external_login", name="uq_repo_contributors_repo_login"),
        )

    # pull_requests
    if "pull_requests" not in existing_tables:
        op.create_table(
            "pull_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False, index=True),
            sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("number", sa.Integer(), nullable=False, index=True),
            sa.Column("title", sa.String(300), nullable=False),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("state", sa.String(32), server_default="open", nullable=False),
            sa.Column("author", sa.String(160), nullable=True),
            sa.Column("author_avatar_url", sa.String(500), nullable=True),
            sa.Column("html_url", sa.String(500), nullable=True),
            sa.Column("merged", sa.Boolean(), server_default="false", nullable=False),
            sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("changed_files_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("commits_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("additions", sa.Integer(), server_default="0", nullable=False),
            sa.Column("deletions", sa.Integer(), server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("repository_id", "number", name="uq_pull_requests_repo_number"),
        )

    # commits
    if "commits" not in existing_tables:
        op.create_table(
            "commits",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("pull_request_id", sa.Integer(), sa.ForeignKey("pull_requests.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("sha", sa.String(64), nullable=False, index=True),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("author_name", sa.String(160), nullable=True),
            sa.Column("author_email", sa.String(320), nullable=True),
            sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("repository_id", "sha", name="uq_commits_repo_sha"),
        )

    # reviews
    if "reviews" not in existing_tables:
        op.create_table(
            "reviews",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("pull_request_id", sa.Integer(), sa.ForeignKey("pull_requests.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("reviewer", sa.String(160), nullable=False, index=True),
            sa.Column("state", sa.String(32), nullable=False),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # changed_files
    if "changed_files" not in existing_tables:
        op.create_table(
            "changed_files",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("pull_request_id", sa.Integer(), sa.ForeignKey("pull_requests.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("filename", sa.String(500), nullable=False, index=True),
            sa.Column("status", sa.String(32), server_default="modified", nullable=False),
            sa.Column("additions", sa.Integer(), server_default="0", nullable=False),
            sa.Column("deletions", sa.Integer(), server_default="0", nullable=False),
            sa.Column("changes", sa.Integer(), server_default="0", nullable=False),
            sa.Column("patch", sa.Text(), nullable=True),
            sa.Column("blob_url", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # jira_projects
    if "jira_projects" not in existing_tables:
        op.create_table(
            "jira_projects",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False, index=True),
            sa.Column("key", sa.String(32), nullable=False, index=True),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("external_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("organization_id", "key", name="uq_jira_projects_org_key"),
        )

    # jira_issues
    if "jira_issues" not in existing_tables:
        op.create_table(
            "jira_issues",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False, index=True),
            sa.Column("jira_project_id", sa.Integer(), sa.ForeignKey("jira_projects.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("key", sa.String(64), nullable=False, index=True),
            sa.Column("summary", sa.String(300), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(64), server_default="Open", nullable=False),
            sa.Column("issue_type", sa.String(64), server_default="Task", nullable=False),
            sa.Column("priority", sa.String(32), server_default="Medium", nullable=False),
            sa.Column("assignee", sa.String(160), nullable=True),
            sa.Column("reporter", sa.String(160), nullable=True),
            sa.Column("external_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("organization_id", "key", name="uq_jira_issues_org_key"),
        )

    # jira_comments
    if "jira_comments" not in existing_tables:
        op.create_table(
            "jira_comments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("jira_issue_id", sa.Integer(), sa.ForeignKey("jira_issues.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("author", sa.String(160), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("external_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # knowledge_checks
    if "knowledge_checks" not in existing_tables:
        op.create_table(
            "knowledge_checks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False, index=True),
            sa.Column("transition_id", sa.Integer(), sa.ForeignKey("transitions.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("knowledge_area_id", sa.Integer(), sa.ForeignKey("knowledge_areas.id"), nullable=False, index=True),
            sa.Column("knowledge_record_id", sa.Integer(), sa.ForeignKey("knowledge_records.id", ondelete="SET NULL"), nullable=True),
            sa.Column("question", sa.Text(), nullable=False),
            sa.Column("expected_knowledge", sa.Text(), server_default="", nullable=False),
            sa.Column("status", sa.String(32), server_default="pending", nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # knowledge_check_attempts
    if "knowledge_check_attempts" not in existing_tables:
        op.create_table(
            "knowledge_check_attempts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("knowledge_check_id", sa.Integer(), sa.ForeignKey("knowledge_checks.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("incoming_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("answer", sa.Text(), nullable=False),
            sa.Column("evaluation_result", sa.String(32), server_default="pending", nullable=False),
            sa.Column("evaluator_type", sa.String(32), server_default="human", nullable=False),
            sa.Column("evaluator_model", sa.String(100), nullable=True),
            sa.Column("feedback", sa.Text(), server_default="", nullable=False),
            sa.Column("verified_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # integration_sync_runs
    if "integration_sync_runs" not in existing_tables:
        op.create_table(
            "integration_sync_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False, index=True),
            sa.Column("integration_id", sa.Integer(), sa.ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("status", sa.String(32), server_default="running", nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("items_synced", sa.Integer(), server_default="0", nullable=False),
            sa.Column("details", sa.JSON(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    for table_name in [
        "integration_sync_runs",
        "knowledge_check_attempts",
        "knowledge_checks",
        "jira_comments",
        "jira_issues",
        "jira_projects",
        "changed_files",
        "reviews",
        "commits",
        "pull_requests",
        "repository_contributors",
        "team_members",
    ]:
        op.drop_table(table_name)
