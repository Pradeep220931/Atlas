"""Track who submitted knowledge records."""

from alembic import op
import sqlalchemy as sa

revision = "0002_knowledge_record_submitter"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("knowledge_records")}
    foreign_keys = inspector.get_foreign_keys("knowledge_records")
    has_submitter_foreign_key = any(
        key["constrained_columns"] == ["submitted_by"] and key["referred_table"] == "users"
        for key in foreign_keys
    )
    if "submitted_by" not in columns or not has_submitter_foreign_key:
        with op.batch_alter_table("knowledge_records") as batch:
            if "submitted_by" not in columns:
                batch.add_column(sa.Column("submitted_by", sa.Integer(), nullable=True))
            if not has_submitter_foreign_key:
                batch.create_foreign_key(
                    "fk_knowledge_records_submitted_by_users",
                    "users",
                    ["submitted_by"],
                    ["id"],
                )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("knowledge_records")}
    foreign_keys = inspector.get_foreign_keys("knowledge_records")
    migration_foreign_key = any(key["name"] == "fk_knowledge_records_submitted_by_users" for key in foreign_keys)
    if "submitted_by" in columns and migration_foreign_key:
        with op.batch_alter_table("knowledge_records") as batch:
            batch.drop_constraint("fk_knowledge_records_submitted_by_users", type_="foreignkey")
            batch.drop_column("submitted_by")
