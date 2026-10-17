# Tests

End-to-end tests run the real code against a real PostgreSQL, a fake website, a fake eBay API and the real
headless browser. The search engine and the AI are simulated inside the test, so results are repeatable.

## What you need
- PostgreSQL 16 (any local instance), Python 3.12 with `requirements.txt` installed (plus `playwright` for the renderer).
- In `/etc/hosts`: `127.0.0.1 dir.test jsdir.test acme.test beta.test`
- Three helpers running:
  ```
  sudo python3 tests/fakeweb.py            # port 80
  python3 tests/fake_ebay.py               # port 3998
  PORT=3999 python3 renderer/server.py     # needs Playwright Chromium
  ```

## Run (v0.5 test, upgrading from v0.4)
```
createdb up5
# 1. make a v0.4 database with the v0.4 code
git worktree add /tmp/ng04 v0.4-commit        # commit from releases.txt
(cd /tmp/ng04 && DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/up5 REDIS_URL=redis://x \
   python3 /path/to/netgate/tests/make_v04_db.py)
# 2. run the test with the current code
DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/up5 REDIS_URL=redis://x SEARXNG_URL=http://127.0.0.1:9 \
OLLAMA_URL=http://127.0.0.1:9 MODEL=qwen3:8b RENDER_URL=http://127.0.0.1:3999 EBAY_API_URL=http://127.0.0.1:3998 \
NO_PROXY=.test,127.0.0.1 python3 tests/test_v05.py
```
The test needs the queue to be a stub that only records calls (`rq.CALLS`); in the AI's build environment small
stubs for `redis`, `rq` and `trafilatura` are put first on `PYTHONPATH`. With real Redis, run workers instead.

It ends with `ALL PASSED` or a list of failures.

## Run (v0.6 test, upgrading from v0.5)
Make a v0.5 database first: run `tests/test_v05.py` with the **v0.5 code** (a worktree of the v0.5 commit from
`releases.txt`) on a fresh v0.4 database, as above. Then, with the current code:
```
DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/up5 REDIS_URL=redis://x SEARXNG_URL=http://127.0.0.1:9 \
OLLAMA_URL=http://127.0.0.1:9 MODEL=qwen3:8b RENDER_URL=http://127.0.0.1:3999 NO_PROXY=.test,127.0.0.1 \
python3 tests/test_v06.py
```
`tests/test_v05.py` also still runs with the current code (v0.4 → v0.7 in one go).

## Run (v0.7 test, upgrading from v0.6)
Make a v0.6 database the same way (run `tests/test_v06.py` with the v0.6 code), then with the current code:
```
DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/up6 REDIS_URL=redis://x SEARXNG_URL=http://127.0.0.1:9 \
OLLAMA_URL=http://127.0.0.1:9 MODEL=qwen3:8b RENDER_URL=http://127.0.0.1:3999 BACKUP_DIR=/tmp/ngbackups \
NO_PROXY=.test,127.0.0.1 python3 tests/test_v07.py
```
`tests/test_v06.py` also runs with the current code (v0.5 → v0.7). The v0.7 test also checks that every feature
in `app/handbook.py` has a Handbook page.
