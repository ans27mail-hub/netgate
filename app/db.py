import os
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Job(Base):
    """One user request: 'find X on the web'."""
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    query: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued/searching/crawling/extracting/done/failed
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Record(Base):
    """One piece of knowledge the AI extracted. Unique per source URL, so re-crawls update instead of duplicating."""
    __tablename__ = "records"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"))
    topic: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    facts: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(Text, unique=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


def init_db():
    Base.metadata.create_all(engine)
