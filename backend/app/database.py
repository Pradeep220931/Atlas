from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

DATABASE_URL = settings.database_url

engine_kwargs: dict = {}
if DATABASE_URL.startswith("postgresql"):
    engine_kwargs.update(
        pool_pre_ping=True,
        pool_recycle=300,
    )
elif DATABASE_URL.startswith("sqlite"):
    engine_kwargs.update(
        connect_args={"check_same_thread": False}
    )

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()