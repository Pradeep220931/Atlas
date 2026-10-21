from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.dialects import postgresql
from app.database import Base
from app.models import entities  # noqa: F401

tables = Base.metadata.sorted_tables
ddl_statements = []

for table in tables:
    create_stmt = str(CreateTable(table).compile(dialect=postgresql.dialect())).strip()
    create_stmt = create_stmt.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ")
    ddl_statements.append(create_stmt + ";")

index_statements = []
for table in tables:
    for index in table.indexes:
        idx_stmt = str(CreateIndex(index).compile(dialect=postgresql.dialect())).strip()
        idx_stmt = idx_stmt.replace("CREATE UNIQUE INDEX ", "CREATE UNIQUE INDEX IF NOT EXISTS ")
        idx_stmt = idx_stmt.replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ")
        index_statements.append(idx_stmt + ";")

alembic_ddl = """
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
INSERT INTO alembic_version (version_num) VALUES ('0004_production_relational_schema') ON CONFLICT DO NOTHING;
"""

full_sql = (
    "\n\n".join(ddl_statements)
    + "\n\n"
    + "\n\n".join(index_statements)
    + "\n\n"
    + alembic_ddl
)

with open("scratch_supabase_schema.sql", "w", encoding="utf-8") as f:
    f.write(full_sql)

print(f"Generated idempotent PostgreSQL DDL for {len(tables)} tables and {len(index_statements)} indexes.")
