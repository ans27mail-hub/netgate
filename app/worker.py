"""Worker start-up (v0.9). `python -m app.worker <queue>` tidies requests left behind by a restart, then runs the
normal RQ worker for that queue: requests that were running are marked “Interrupted (NetGate restarted)” and
waiting ones are queued again. Also kept so jobs queued by v0.2 (app.worker.run_job) still run after an update."""
import os
import sys
import time

from .jobs import run_job  # noqa: F401


def main():
    queue = sys.argv[1] if len(sys.argv) > 1 else "netgate"
    url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    from .control import worker_started
    from .db import SessionLocal, init_db, log
    for _ in range(30):   # the web app may still be creating / upgrading the tables
        try:
            init_db()
            with SessionLocal() as s:
                n, q = worker_started(s, night=(queue == "netgate-night"))
            if n or q:
                log("info", "worker", f"{queue}: {n} request(s) marked interrupted, {q} waiting request(s) queued again")
            break
        except Exception as e:  # noqa: BLE001
            print(f"worker start-up: {type(e).__name__}: {e}", flush=True)
            time.sleep(5)
    os.execvp("rq", ["rq", "worker", queue, "--url", url])


if __name__ == "__main__":
    main()
