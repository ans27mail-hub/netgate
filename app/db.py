import os
import re
from datetime import datetime

from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
                        create_engine, func, select, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Setting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Group(Base):
    """A directory section, e.g. Manufacturers."""
    __tablename__ = "groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    instructions: Mapped[str] = mapped_column(Text, default="")   # told to the AI
    search_terms: Mapped[str] = mapped_column(Text, default="")   # added to every keyword search
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    keywords: Mapped[list["Keyword"]] = relationship(order_by="Keyword.id", cascade="all, delete-orphan",
                                                     back_populates="group", lazy="selectin")
    fields: Mapped[list["Field"]] = relationship(order_by="Field.position", cascade="all, delete-orphan",
                                                 back_populates="group", lazy="selectin")


class Keyword(Base):
    __tablename__ = "keywords"
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)
    group: Mapped[Group] = relationship(back_populates="keywords")


FIELD_TYPES = {"text": "Text", "list": "List", "choice": "Choice", "number": "Number",
               "email": "Email", "url": "Website"}


class Field(Base):
    """A per-group field the AI fills, e.g. City or Employees."""
    __tablename__ = "fields"
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    key: Mapped[str] = mapped_column(String(80))
    type: Mapped[str] = mapped_column(String(20), default="text")
    choices: Mapped[str] = mapped_column(Text, default="")        # comma separated, for type=choice
    filter: Mapped[bool] = mapped_column(Boolean, default=False)
    sort: Mapped[bool] = mapped_column(Boolean, default=False)
    card: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    group: Mapped[Group] = relationship(back_populates="fields")

    def choice_list(self) -> list[str]:
        return [c.strip() for c in (self.choices or "").split(",") if c.strip()]


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str] = mapped_column(String(20), default="Viewer")
    perms: Mapped[str] = mapped_column(Text, default="view")       # comma separated permission keys
    all_groups: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    group_links: Mapped[list["UserGroup"]] = relationship(cascade="all, delete-orphan", lazy="selectin")

    @property
    def perm_set(self) -> set[str]:
        return {p for p in (self.perms or "").split(",") if p}

    @property
    def group_ids(self) -> set[int]:
        return {link.group_id for link in self.group_links}


class UserGroup(Base):
    __tablename__ = "user_groups"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)


class Job(Base):
    """One AI run: a typed request, or a keyword update."""
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    query: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued/searching/crawling/extracting/done/failed
    message: Mapped[str | None] = mapped_column(Text)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20), default="request")    # request / keyword
    saved: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Record(Base):
    """One directory listing. Unique per group + source URL, so re-crawls update instead of duplicating."""
    __tablename__ = "records"
    __table_args__ = (UniqueConstraint("group_id", "source_url", name="records_group_source"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    topic: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    facts: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSONB, default=dict)          # values of the group's fields
    source_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# Upgrades for databases created by earlier versions. Every statement is safe to run again.
MIGRATIONS = [
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS kind VARCHAR(20) NOT NULL DEFAULT 'request'",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS saved INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS updated INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS group_id INTEGER REFERENCES groups(id) ON DELETE CASCADE",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS data JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT now()",
    "ALTER TABLE records DROP CONSTRAINT IF EXISTS records_source_url_key",
    "CREATE UNIQUE INDEX IF NOT EXISTS records_group_source ON records (group_id, source_url)",
]

EMPLOYEE_RANGES = "1–10, 11–50, 51–200, 201–500, 500+"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:60] or "field"


def default_fields() -> list[Field]:
    return [
        Field(name="City", key="city", type="text", filter=True, sort=True, card=True, position=1),
        Field(name="Country", key="country", type="text", filter=True, sort=False, card=False, position=2),
    ]


def _seed(s):
    """Create starter groups once. Never re-runs, even if the admin deletes them later."""
    if s.get(Setting, "seeded"):
        return
    starters = [
        ("Manufacturers", "Factories and workshops: what they make, where they are, and how big they are.",
         "manufacturer", ["motorcycle jackets", "leather gloves", "textile suits", "riding boots", "protective armour"]),
        ("Materials", "Suppliers of leather, textiles, armour, zips, trims and other components.", "supplier", []),
        ("Standards", "Safety standards, test labs and certification bodies.", "", []),
        ("Trade shows", "Trade fairs and exhibitions: dates, venues and who exhibits.", "trade fair", []),
        ("Logistics", "Freight forwarders, ports, routes and shipping services.", "", []),
        ("Buyers & brands", "Brands and retailers that buy and sell these products.", "", []),
    ]
    for i, (name, instr, terms, kws) in enumerate(starters):
        if s.scalar(select(Group).where(Group.name == name)):
            continue
        g = Group(name=name, instructions=instr, search_terms=terms, position=i)
        g.fields = default_fields()
        if name == "Manufacturers":
            g.fields += [
                Field(name="Products", key="products", type="list", filter=True, card=True, position=3),
                Field(name="Employees", key="employees", type="choice", choices=EMPLOYEE_RANGES,
                      filter=True, sort=True, card=True, position=4),
                Field(name="Contact email", key="contact_email", type="email", position=5),
            ]
        g.keywords = [Keyword(text=k) for k in kws]
        s.add(g)
    s.add(Setting(key="seeded", value="1"))


def init_db():
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for stmt in MIGRATIONS:
            conn.execute(text(stmt))
    with SessionLocal() as s:
        _seed(s)
        s.commit()
