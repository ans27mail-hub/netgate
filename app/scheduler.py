"""Starts the night batch when the night window opens. Runs as its own small container."""
import os
import time
from datetime import datetime

from redis import Redis
from rq import Queue
from sqlalchemy import select

from .db import Job, NightRun, SessionLocal, init_db
from .jobs import in_window, local_now, night_date, night_settings

night_queue = Queue("netgate-night", connection=Redis.from_url(os.environ["REDIS_URL"]))


def tick():
    with SessionLocal() as s:
        cfg = night_settings(s)
        if not cfg.get("enabled"):
            return
        now = local_now(cfg)
        if not in_window(cfg, now):
            return
        nd = night_date(cfg, now)
        if nd.weekday() not in [int(d) for d in cfg.get("days", [])]:
            return
        if s.scalar(select(NightRun).where(NightRun.night_date == nd)):
            return  # tonight's run already started
        run = NightRun(night_date=nd, status="running", stats={})
        job = Job(query=f"Night run {nd.isoformat()}", kind="night")
        s.add_all([run, job])
        s.commit()
        night_queue.enqueue("app.jobs.run_job", job.id, run_id=run.id, job_timeout=14 * 3600)
        print(f"{datetime.now():%Y-%m-%d %H:%M} night run {run.id} started", flush=True)


def main():
    for _ in range(30):  # wait for the web app to create/upgrade the tables
        try:
            init_db()
            break
        except Exception:
            time.sleep(5)
    while True:
        try:
            tick()
        except Exception as e:
            print(f"scheduler: {type(e).__name__}: {e}", flush=True)
        time.sleep(60)


if __name__ == "__main__":
    main()
