import os

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from redis import Redis
from rq import Queue
from sqlalchemy import or_, select

from .db import Job, Record, SessionLocal, init_db
from .worker import run_job

app = FastAPI(title="NetGate")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
queue = Queue("netgate", connection=Redis.from_url(os.environ["REDIS_URL"]))


@app.on_event("startup")
def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    with SessionLocal() as s:
        jobs = s.scalars(select(Job).order_by(Job.id.desc()).limit(20)).all()
    return templates.TemplateResponse(request, "index.html", {"jobs": jobs})


@app.post("/jobs")
def create_job(query: str = Form(...)):
    with SessionLocal() as s:
        job = Job(query=query.strip())
        s.add(job)
        s.commit()
        job_id = job.id
    queue.enqueue(run_job, job_id, job_timeout=1800)
    return RedirectResponse("/", status_code=303)


@app.get("/jobs/table", response_class=HTMLResponse)
def jobs_table(request: Request):
    """Polled by HTMX every few seconds to show live job status."""
    with SessionLocal() as s:
        jobs = s.scalars(select(Job).order_by(Job.id.desc()).limit(20)).all()
    return templates.TemplateResponse(request, "_jobs.html", {"jobs": jobs})


@app.get("/records", response_class=HTMLResponse)
def records(request: Request, q: str = ""):
    with SessionLocal() as s:
        stmt = select(Record).order_by(Record.updated_at.desc()).limit(200)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(or_(Record.title.ilike(like), Record.summary.ilike(like),
                                  Record.facts.ilike(like), Record.topic.ilike(like)))
        rows = s.scalars(stmt).all()
    return templates.TemplateResponse(request, "records.html", {"records": rows, "q": q})


@app.get("/health")
def health():
    return {"ok": True}
