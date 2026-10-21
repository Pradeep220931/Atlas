"""Store evidence-backed Claude gap analysis."""

from alembic import op
import sqlalchemy as sa

revision = "0003_knowledge_gap_ai_analysis"
down_revision = "0002_knowledge_record_submitter"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("knowledge_gaps")}
    if "ai_analysis" not in columns:
        op.add_column("knowledge_gaps", sa.Column("ai_analysis", sa.JSON(), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("knowledge_gaps")}
    if "ai_analysis" in columns:
        op.drop_column("knowledge_gaps", "ai_analysis")
