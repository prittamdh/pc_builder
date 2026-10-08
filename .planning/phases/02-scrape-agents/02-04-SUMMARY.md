# 02-04 Summary: agent API and /health/pipeline

Worked inline, test-first. Done before 02-03 at the owner's request (2026-09-25): the
goal is a working extension on several machines first; the worker follows.
Requirements: AGENT-04 (endpoint side), AGENT-06 (via 02-02's processor), AGENT-12.

## What was built

- **`src/api/routes/agent.py`**: `POST /api/agent/lease`, `/result`, `/heartbeat`, as in
  `docs/AGENT_PROTOCOL.md`.
  - Bearer token checked on every call; 401 with `WWW-Authenticate: Bearer` otherwise.
  - Rate-limited per token and endpoint (`RATE_LIMIT_AGENT`, default 120/minute; the
    token is hashed before it becomes a limiter key).
  - Bodies are read with a size cap before JSON parsing: 8 MB for results, 64 KB for the
    others; over that is 413. A 6 MB page still gets in and is stored as `rejected`
    with its reason, per the roadmap's success criterion 4. Bad JSON or fields: 400.
  - Stale lease: 409. The agent is told only `job_id`, `status`, `reason`.
  - DB work runs in the threadpool so a big upload doesn't block other requests.
  - Left out of the OpenAPI schema.
- **`GET /health/pipeline`** (`src/pipeline/health.py`): 503 when no agent has checked in
  for 24 h, no price was saved for 24 h, or a scheduled task's latest run failed or is
  more than 2 intervals late. `SCHEDULED_TASKS` is empty until the worker (02-03) fills
  it. Also reports job counts per status (failed jobs are counted there).
- `RATE_LIMIT_AGENT` in settings and `.env.example`.

## Notes

- Extension service workers aren't subject to CORS for hosts in their
  `host_permissions`, so the CORS allow-list is unchanged.
- A request with a bad token is refused before the limiter counts it; tokens are 256-bit,
  so guessing isn't a practical risk.

## Tests

`tests/test_agent_api.py` (29): auth on all three endpoints, revoke, schema exclusion,
per-token limit, lease shape, save-once replay, 409, the four doctored uploads from
success criterion 4, 413, 400, heartbeat, and four health cases.
