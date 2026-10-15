import json
import os
import re
from datetime import datetime

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, func,
                        select, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Setting(Base):
    """Key/value settings. Values are stored as JSON text."""
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Group(Base):
    """A directory section, e.g. Manufacturers."""
    __tablename__ = "groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    instructions: Mapped[str] = mapped_column(Text, default="")          # what belongs here (Discover)
    enrich_instructions: Mapped[str] = mapped_column(Text, default="")   # how to fill fields (Enrich)
    ignore_instructions: Mapped[str] = mapped_column(Text, default="")   # what to skip
    search_terms: Mapped[str] = mapped_column(Text, default="")          # added to every Discover search
    position: Mapped[int] = mapped_column(Integer, default=0)
    night_discover: Mapped[bool] = mapped_column(Boolean, default=True)
    night_enrich: Mapped[bool] = mapped_column(Boolean, default=True)
    refresh_days: Mapped[int] = mapped_column(Integer, default=0)        # 0 = never refresh
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
    night: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    found_count: Mapped[int] = mapped_column(Integer, default=0)
    group: Mapped[Group] = relationship(back_populates="keywords")


FIELD_TYPES = {"text": "Text", "list": "List", "choice": "Choice", "number": "Number",
               "email": "Email", "url": "Website", "phone": "Phone"}
DISCOVER_KEYS = ("city", "country", "website")


class Field(Base):
    """A per-group field the AI fills, e.g. City or Employees."""
    __tablename__ = "fields"
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    key: Mapped[str] = mapped_column(String(80))
    type: Mapped[str] = mapped_column(String(20), default="text")
    choices: Mapped[str] = mapped_column(Text, default="")        # comma separated, for type=choice
    words: Mapped[str] = mapped_column(Text, default="")          # search words used by Enrich
    stage: Mapped[str] = mapped_column(String(20), default="enrich")  # discover / enrich
    filter: Mapped[bool] = mapped_column(Boolean, default=False)
    sort: Mapped[bool] = mapped_column(Boolean, default=False)
    card: Mapped[bool] = mapped_column(Boolean, default=False)
    list: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    group: Mapped[Group] = relationship(back_populates="fields")

    def choice_list(self) -> "list[str]":
        return [c.strip() for c in (self.choices or "").split(",") if c.strip()]

    def word_list(self) -> "list[str]":
        return [w.strip() for w in (self.words or "").split(",") if w.strip()]


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
    prefs: Mapped[dict] = mapped_column(JSONB, default=dict)       # view, list columns, display
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
    """One AI run: discover (request/keyword), enrich, night batch."""
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    query: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    message: Mapped[str | None] = mapped_column(Text)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"))
    record_id: Mapped[int | None] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20), default="request")   # request / keyword / enrich / night
    saved: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Record(Base):
    """One directory listing (a company). Matched by website domain, or by name + city."""
    __tablename__ = "records"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    topic: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    facts: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSONB, default=dict)          # values of the group's fields
    sources: Mapped[dict] = mapped_column(JSONB, default=dict)       # field key -> page it came from
    social: Mapped[dict] = mapped_column(JSONB, default=dict)        # facebook / instagram / linkedin -> url
    source_url: Mapped[str] = mapped_column(Text)                    # page where it was first found
    name_key: Mapped[str | None] = mapped_column(Text, index=True)
    domain: Mapped[str | None] = mapped_column(Text, index=True)
    enrich_runs: Mapped[int] = mapped_column(Integer, default=0)
    last_enriched_at: Mapped[datetime | None] = mapped_column(DateTime)
    enrich_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AIServer(Base):
    __tablename__ = "ai_servers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), default="ollama")   # ollama / openrouter
    url: Mapped[str] = mapped_column(Text, default="")
    api_key: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AIUsage(Base):
    """Cost log for paid providers (OpenRouter)."""
    __tablename__ = "ai_usage"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    server_id: Mapped[int | None] = mapped_column(Integer)
    job_type: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(Text)
    cost: Mapped[float] = mapped_column(Float, default=0.0)


class NightRun(Base):
    __tablename__ = "night_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    night_date: Mapped[datetime] = mapped_column(Date, unique=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    note: Mapped[str | None] = mapped_column(Text)


# Upgrades for databases created by earlier versions. Every statement is safe to run again.
MIGRATIONS = [
    # v0.2
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS kind VARCHAR(20) NOT NULL DEFAULT 'request'",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS saved INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS updated INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS group_id INTEGER REFERENCES groups(id) ON DELETE CASCADE",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS data JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT now()",
    "ALTER TABLE records DROP CONSTRAINT IF EXISTS records_source_url_key",
    # v0.3: one page can hold many companies, so listings are no longer unique per page
    "ALTER TABLE records DROP CONSTRAINT IF EXISTS records_group_source",
    "DROP INDEX IF EXISTS records_group_source",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS sources JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS social JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS name_key TEXT",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS domain TEXT",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS enrich_runs INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS last_enriched_at TIMESTAMP",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS enrich_note TEXT",
    "CREATE INDEX IF NOT EXISTS ix_records_group_id ON records (group_id)",
    "CREATE INDEX IF NOT EXISTS ix_records_name_key ON records (name_key)",
    "CREATE INDEX IF NOT EXISTS ix_records_domain ON records (domain)",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS record_id INTEGER",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS stats JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE groups ADD COLUMN IF NOT EXISTS enrich_instructions TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE groups ADD COLUMN IF NOT EXISTS ignore_instructions TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE groups ADD COLUMN IF NOT EXISTS night_discover BOOLEAN NOT NULL DEFAULT true",
    "ALTER TABLE groups ADD COLUMN IF NOT EXISTS night_enrich BOOLEAN NOT NULL DEFAULT true",
    "ALTER TABLE groups ADD COLUMN IF NOT EXISTS refresh_days INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE keywords ADD COLUMN IF NOT EXISTS night BOOLEAN NOT NULL DEFAULT true",
    "ALTER TABLE keywords ADD COLUMN IF NOT EXISTS last_run_at TIMESTAMP",
    "ALTER TABLE keywords ADD COLUMN IF NOT EXISTS found_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE fields ADD COLUMN IF NOT EXISTS words TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE fields ADD COLUMN IF NOT EXISTS stage VARCHAR(20) NOT NULL DEFAULT 'enrich'",
    "ALTER TABLE fields ADD COLUMN IF NOT EXISTS list BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS prefs JSONB NOT NULL DEFAULT '{}'::jsonb",
]

EMPLOYEE_RANGES = "1–10, 11–50, 51–200, 201–500, 500+"

DEFAULT_WORDS = {
    "city": "address, located in", "country": "address", "website": "official website",
    "products": "products, we manufacture, product range", "employees": "employees, staff, workers, workforce",
    "contact_email": "contact, email, enquiry", "phone": "phone, contact, call",
}

LEGAL_WORDS = r"\b(pvt|private|ltd|limited|llc|inc|co|company|corp|corporation|gmbh|srl|spa|plc|the|and|&)\b"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:60] or "field"


def name_key(name: str | None) -> str:
    """'Acme Leather (Pvt.) Ltd.' -> 'acme leather' for matching the same company."""
    s = re.sub(r"[^a-z0-9& ]+", " ", (name or "").lower())
    s = re.sub(LEGAL_WORDS, " ", s)
    return re.sub(r"\s+", " ", s).strip()


def url_domain(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip().lower()
    if "://" not in url:
        url = "http://" + url
    host = url.split("://", 1)[1].split("/")[0].split(":")[0]
    host = host.removeprefix("www.")
    return host if "." in host else None


def default_fields() -> list[Field]:
    return [
        Field(name="City", key="city", type="text", stage="discover", words=DEFAULT_WORDS["city"],
              filter=True, sort=True, card=True, list=True, position=1),
        Field(name="Country", key="country", type="text", stage="discover", words=DEFAULT_WORDS["country"],
              filter=True, card=True, position=2),
        Field(name="Website", key="website", type="url", stage="discover", words=DEFAULT_WORDS["website"],
              list=True, position=3),
    ]


def get_setting(s, key: str, default=None):
    row = s.get(Setting, key)
    if not row:
        return default
    try:
        return json.loads(row.value)
    except (ValueError, TypeError):
        return row.value


def set_setting(s, key: str, value):
    row = s.get(Setting, key)
    if row:
        row.value = json.dumps(value)
    else:
        s.add(Setting(key=key, value=json.dumps(value)))


def _seed(s):
    """Create starter groups once. Never re-runs, even if the admin deletes them later."""
    if s.get(Setting, "seeded"):
        return
    starters = [
        ("Manufacturers", "Companies that manufacture the products themselves (factories and workshops).",
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
                Field(name="Products", key="products", type="list", words=DEFAULT_WORDS["products"],
                      filter=True, card=True, list=True, position=4),
                Field(name="Employees", key="employees", type="choice", choices=EMPLOYEE_RANGES,
                      words=DEFAULT_WORDS["employees"], filter=True, sort=True, card=True, list=True, position=5),
                Field(name="Contact email", key="contact_email", type="email", words=DEFAULT_WORDS["contact_email"],
                      list=True, position=6),
            ]
        g.keywords = [Keyword(text=k) for k in kws]
        s.add(g)
    s.add(Setting(key="seeded", value="1"))


def _upgrade_v03(s):
    """One-time data changes for v0.3 on existing installs."""
    if s.get(Setting, "v03_upgraded"):
        return
    for g in s.scalars(select(Group)).all():
        keys = {f.key for f in g.fields}
        if "website" not in keys:
            pos = max([f.position for f in g.fields] or [0]) + 1
            g.fields.append(Field(name="Website", key="website", type="url", stage="discover",
                                  words=DEFAULT_WORDS["website"], list=True, position=pos))
        for f in g.fields:
            if f.key in DISCOVER_KEYS:
                f.stage = "discover"
            if not f.words and f.key in DEFAULT_WORDS:
                f.words = DEFAULT_WORDS[f.key]
            if f.card:
                f.list = True
    for r in s.scalars(select(Record).where(Record.name_key.is_(None))).all():
        r.name_key = name_key(r.title)
        r.domain = url_domain((r.data or {}).get("website"))
    s.add(Setting(key="v03_upgraded", value="1"))


def _seed_ai(s):
    """First AI server comes from .env (the iMac); every job uses it until changed in Settings."""
    if s.scalar(select(func.count(AIServer.id))):
        return
    url = os.environ.get("OLLAMA_URL", "").strip()
    if not url:
        return
    server = AIServer(name="iMac (Ollama)", kind="ollama", url=url)
    s.add(server)
    s.flush()
    model = os.environ.get("MODEL", "qwen3:8b")
    for job in ("discover", "enrich", "night"):
        set_setting(s, f"ai.{job}", {"server": server.id, "model": model})
    set_setting(s, "ai.fallback", {"server": server.id, "model": model})


def init_db():
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for stmt in MIGRATIONS:
            conn.execute(text(stmt))
    with SessionLocal() as s:
        _seed(s)
        s.flush()
        _upgrade_v03(s)
        _seed_ai(s)
        s.commit()
