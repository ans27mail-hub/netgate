"""Starts the night batch when the night window opens. Runs as its own small container."""
import os
import time
from datetime import datetime

from redis import Redis
from rq import Queue
from sqlalchemy import select

from .db import Job, NightRun, SessionLocal, init_db, log
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
        s.add(run)
        s.flush()
        job = Job(query=f"Night run {nd.isoformat()}", kind="night", params={"run_id": run.id}, stats={})
        s.add(job)
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
    last_purge = 0.0
    while True:
        try:
            tick()
        except Exception as e:
            print(f"scheduler: {type(e).__name__}: {e}", flush=True)
            log("error", "scheduler", f"{type(e).__name__}: {e}")
        if time.time() - last_purge > 3600:   # once an hour: old cached pages, deleted requests, old traces
            try:
                from .control import purge_deleted
                from .crawl import purge_cache
                n = purge_cache()
                with SessionLocal() as s:
                    m = purge_deleted(s)
                    s.commit()
                if n or m:
                    print(f"scheduler: removed {n} old cached pages, {m} deleted requests", flush=True)
            except Exception as e:
                print(f"scheduler: cleanup failed: {type(e).__name__}: {e}", flush=True)
                log("warning", "scheduler", f"Cleanup failed: {type(e).__name__}: {e}")
            last_purge = time.time()
        time.sleep(60)


if __name__ == "__main__":
    main()
