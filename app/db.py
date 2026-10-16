import json
import os
import re
from datetime import datetime

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text,
                        create_engine, func, select, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .auth import ADMIN, DEFAULT_ROLES, OLD_PERMS, PERM_KEYS, best_role, join, split

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
    """A directory, e.g. Manufacturers or Online retailers. (Called "group" in the code and database.)"""
    __tablename__ = "groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    methods: Mapped[dict] = mapped_column(JSONB, default=dict)          # search method key -> its options
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
    method: Mapped[str] = mapped_column(String(20), default="all")    # which find method runs it ("all" = every one)
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
    source: Mapped[str] = mapped_column(String(60), default="")       # "Filled from": '' = AI + code, or e.g. ebay:feedback_pct
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


class Role(Base):
    """A named set of permissions. Changing a role changes every user who has it."""
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    perms: Mapped[str] = mapped_column(Text, default="view")         # comma separated permission keys
    locked: Mapped[bool] = mapped_column(Boolean, default=False)     # Admin: always everything
    all_groups: Mapped[bool] = mapped_column(Boolean, default=True)  # default directory access for new users
    group_ids: Mapped[list] = mapped_column(JSONB, default=list)
    position: Mapped[int] = mapped_column(Integer, default=0)

    @property
    def perm_set(self) -> set[str]:
        return set(PERM_KEYS) if self.locked else split(self.perms)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)  # kept in step with the Admin role
    role: Mapped[str] = mapped_column(String(60), default="Viewer")  # role name (shown in lists)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id", ondelete="SET NULL"))
    perms: Mapped[str] = mapped_column(Text, default="view")       # v0.4 permissions, kept for rollback
    extra_perms: Mapped[str] = mapped_column(Text, default="")     # this person only: added to the role
    removed_perms: Mapped[str] = mapped_column(Text, default="")   # this person only: taken from the role
    all_groups: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    prefs: Mapped[dict] = mapped_column(JSONB, default=dict)       # view, list columns, display, saved views
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    group_links: Mapped[list["UserGroup"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    role_obj: Mapped[Role | None] = relationship(lazy="joined")

    @property
    def perm_set(self) -> set[str]:
        if self.is_admin:
            return set(PERM_KEYS)
        base = self.role_obj.perm_set if self.role_obj else set()
        return (base | split(self.extra_perms)) - split(self.removed_perms)

    @property
    def custom(self) -> bool:
        """Has permissions of its own on top of (or taken from) the role."""
        return bool(split(self.extra_perms) or split(self.removed_perms))

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
    params: Mapped[dict] = mapped_column(JSONB, default=dict)        # keyword_id, method, run_id, steps …
    control: Mapped[str] = mapped_column(String(10), default="")    # '' / pause / stop: asked by the user
    state: Mapped[dict] = mapped_column(JSONB, default=dict)         # where a paused job got to (for Resume)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)    # in the Deleted bin (kept 30 days)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class JobTrace(Base):
    """Debug view: what a job read, what code found, what the AI was asked and answered."""
    __tablename__ = "job_traces"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    kind: Mapped[str] = mapped_column(String(20))      # search / page / code / ai / note / error
    url: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSONB, default=dict)


class RejectedKeyword(Base):
    """Keywords that are never searched again (until restored)."""
    __tablename__ = "rejected_keywords"
    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    norm: Mapped[str] = mapped_column(Text, index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))   # None = everywhere
    reason: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    job_id: Mapped[int | None] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Record(Base):
    """One contact (a company or store). It exists once and can be in several directories (Membership).
    Matched by marketplace id, website domain, or name + city."""
    __tablename__ = "records"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"), index=True)  # first directory (v0.4)
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
    links: Mapped[dict] = mapped_column(JSONB, default=dict)         # marketplace / store pages: ebay, etsy, amazon …
    ext: Mapped[dict] = mapped_column(JSONB, default=dict)           # ids on other sites, e.g. {"ebay": "seller_name"}
    history: Mapped[list] = mapped_column(JSONB, default=list)       # plain-text notes: how and when it was found
    notes: Mapped[str] = mapped_column(Text, default="")             # notes typed by a person
    enrich_tonight: Mapped[bool] = mapped_column(Boolean, default=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)   # first accepted into a directory
    vec: Mapped[bytes | None] = mapped_column(LargeBinary)           # embedding used for AI suggestions
    vec_model: Mapped[str | None] = mapped_column(Text)
    added_by: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Membership(Base):
    """A contact accepted into a directory."""
    __tablename__ = "memberships"
    record_id: Mapped[int] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True, index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    added_by: Mapped[int | None] = mapped_column(Integer)


class InboxItem(Base):
    """A contact waiting for a decision for one directory (or "not sure yet" when group_id is None)."""
    __tablename__ = "inbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(12), default="new", index=True)   # new / accepted / rejected
    method: Mapped[str] = mapped_column(String(20), default="web")   # how it was found: web / directory / ebay / manual …
    keyword: Mapped[str] = mapped_column(Text, default="")
    job_id: Mapped[int | None] = mapped_column(Integer)
    found_url: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float | None] = mapped_column(Float)               # AI suggestion confidence 0..1
    suggest: Mapped[str | None] = mapped_column(String(10))          # accept / reject
    why: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")            # reject reason
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    decided_by: Mapped[int | None] = mapped_column(Integer)


class Decision(Base):
    """Every accept / reject, kept to improve suggestions and to export as training data."""
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    user_id: Mapped[int | None] = mapped_column(Integer)
    record_id: Mapped[int | None] = mapped_column(ForeignKey("records.id", ondelete="SET NULL"), index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"))
    decision: Mapped[str] = mapped_column(String(12))                # accept / reject / restore / remove
    reason: Mapped[str] = mapped_column(Text, default="")
    method: Mapped[str] = mapped_column(String(20), default="")
    keyword: Mapped[str] = mapped_column(Text, default="")
    snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)


class AppLog(Base):
    """NetGate's own log: errors and notable events from the web app, workers and scheduler."""
    __tablename__ = "app_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    level: Mapped[str] = mapped_column(String(10), default="info")
    source: Mapped[str] = mapped_column(String(30), default="")
    message: Mapped[str] = mapped_column(Text)
    detail: Mapped[str] = mapped_column(Text, default="")


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


class PageCache(Base):
    """Downloaded pages kept for a few days, so re-runs don't download everything again."""
    __tablename__ = "page_cache"
    url: Mapped[str] = mapped_column(Text, primary_key=True)
    final_url: Mapped[str] = mapped_column(Text, default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    status: Mapped[int] = mapped_column(Integer, default=0)       # 0 = could not read
    rendered: Mapped[bool] = mapped_column(Boolean, default=False)
    html_gz: Mapped[bytes | None] = mapped_column(LargeBinary)
    text: Mapped[str | None] = mapped_column(Text)


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
    # v0.5: directories, inbox, roles, request controls
    """DO $$ BEGIN
         IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'records_group_id_fkey' AND confdeltype = 'c') THEN
           ALTER TABLE records DROP CONSTRAINT records_group_id_fkey;
           ALTER TABLE records ADD CONSTRAINT records_group_id_fkey FOREIGN KEY (group_id)
             REFERENCES groups(id) ON DELETE SET NULL;
         END IF;
       END $$""",
    "ALTER TABLE groups ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE groups ADD COLUMN IF NOT EXISTS methods JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE keywords ADD COLUMN IF NOT EXISTS method VARCHAR(20) NOT NULL DEFAULT 'all'",
    "ALTER TABLE fields ADD COLUMN IF NOT EXISTS source VARCHAR(60) NOT NULL DEFAULT ''",
    "ALTER TABLE users ALTER COLUMN role TYPE VARCHAR(60)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS role_id INTEGER REFERENCES roles(id) ON DELETE SET NULL",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS extra_perms TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS removed_perms TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS params JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS control VARCHAR(10) NOT NULL DEFAULT ''",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS state JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS started_at TIMESTAMP",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS finished_at TIMESTAMP",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS links JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS ext JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS history JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS notes TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS enrich_tonight BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMP",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS vec BYTEA",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS vec_model TEXT",
    "ALTER TABLE records ADD COLUMN IF NOT EXISTS added_by INTEGER",
    "CREATE INDEX IF NOT EXISTS ix_records_ext ON records USING gin (ext)",
    "CREATE INDEX IF NOT EXISTS ix_jobs_status ON jobs (status)",
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


DEFAULT_METHODS = {"web": {}, "website": {}}   # Web search to find, Company website to enrich


def log(level: str, source: str, message: str, detail: str = ""):
    """Write to NetGate's own log (Developer tools → Logs). Never raises."""
    try:
        with SessionLocal() as s:
            s.add(AppLog(level=level, source=source[:30], message=str(message)[:2000], detail=str(detail)[:20000]))
            s.commit()
    except Exception:
        pass


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
        g = Group(name=name, instructions=instr, search_terms=terms, position=i, methods=dict(DEFAULT_METHODS))
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


def _seed_roles(s):
    """Starting roles. Added once; afterwards admins edit them on the Roles page."""
    have = {r.name for r in s.scalars(select(Role)).all()}
    for i, (name, desc, perms) in enumerate(DEFAULT_ROLES):
        if name not in have and not s.get(Setting, "roles_seeded"):
            s.add(Role(name=name, description=desc, perms=join(perms), locked=(name == ADMIN), position=i))
    admin = s.scalar(select(Role).where(Role.name == ADMIN))
    if admin and not admin.locked:
        admin.locked = True
    if not s.get(Setting, "roles_seeded"):
        s.add(Setting(key="roles_seeded", value="1"))


def _upgrade_v05(s):
    """One-time data changes for v0.5 on existing installs. Nothing is deleted."""
    if s.get(Setting, "v05_upgraded"):
        return
    # groups become directories with the two methods v0.4 used
    for g in s.scalars(select(Group)).all():
        if not g.methods:
            g.methods = dict(DEFAULT_METHODS)
    # every existing listing is an accepted contact of its group
    member = {(m.record_id, m.group_id) for m in s.scalars(select(Membership)).all()}
    for r in s.scalars(select(Record)).all():
        if r.group_id and (r.id, r.group_id) not in member:
            s.add(Membership(record_id=r.id, group_id=r.group_id, added_at=r.created_at))
        if r.group_id and not r.accepted_at:
            r.accepted_at = r.created_at or datetime.utcnow()
        if not r.history:
            when = r.created_at.strftime("%d %b %Y") if r.created_at else ""
            r.history = [{"at": r.created_at.isoformat() if r.created_at else "",
                          "text": f"Found by “{(r.topic or '')[:80]}” · {when}"}]
    # users get the role closest to their permissions; exceptions keep their exact access
    roles = s.scalars(select(Role)).all()
    by_name = {r.name: r for r in roles}
    for u in s.scalars(select(User)).all():
        if u.role_id:
            continue
        if u.is_admin:
            u.role_id, u.role = by_name[ADMIN].id, ADMIN
            continue
        target = set()
        for p in split(u.perms):
            target |= set(OLD_PERMS.get(p, [p] if p in PERM_KEYS else []))
        if {"request", "keywords"} & target:
            target.add("requests_own")
        named = {"Editor": "Researcher", "Viewer": "Viewer"}.get(u.role)
        role = by_name.get(named) if named else None
        if role:
            rp = split(role.perms)
            extra, removed = target - rp, rp - target
        else:
            role, extra, removed = best_role(target, roles)
        u.role_id, u.role = (role.id, role.name) if role else (None, "Custom")
        u.extra_perms, u.removed_perms = join(extra), join(removed)
    s.add(Setting(key="v05_upgraded", value="1"))


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
    # the web app and the scheduler both start this; the lock makes them take turns
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(424242)"))
        Base.metadata.create_all(conn)
        for stmt in MIGRATIONS:
            conn.execute(text(stmt))
    with SessionLocal() as s:
        s.execute(text("SELECT pg_advisory_xact_lock(424243)"))
        _seed(s)
        s.flush()
        _upgrade_v03(s)
        _seed_roles(s)
        s.flush()
        _upgrade_v05(s)
        _seed_ai(s)
        s.commit()
