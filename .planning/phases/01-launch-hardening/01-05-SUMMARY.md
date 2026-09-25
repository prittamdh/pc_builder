---
phase: 01-launch-hardening
plan: 05
status: done
---

# Plan 01-05 Summary: Rate limits, image-proxy streaming cap, save-build caps

## What shipped

- **Task 1 (owner checkpoint):** resolved before this session started - owner
  approved `slowapi==0.1.10` on 2026-09-25 (PyPI/GitHub metadata checked by the
  manager: `github.com/laurents/slowapi`, MIT, author Laurent Savaete).
- **SEC-03 (rate limiting):** new `src/api/rate_limit.py` holds the shared
  `Limiter` (`key_func=rate_limit_key`, `default_limits=[lambda: settings.RATE_LIMIT_DEFAULT]`,
  `enabled=settings.RATE_LIMIT_ENABLED`) and `rate_limit_key(request)`, which
  returns `CF-Connecting-IP` only when `settings.TRUST_CF_CONNECTING_IP` is
  true and the header is present, otherwise `get_remote_address(request)`.
  `RATE_LIMIT_IMAGES`/`RATE_LIMIT_BUILDER`/`RATE_LIMIT_SAVE_BUILD`/
  `RATE_LIMIT_DEFAULT`/`TRUST_CF_CONNECTING_IP` are all read live off the
  shared `configs.settings` module (never captured once at import time), so
  tests can `monkeypatch.setattr(settings, ...)` directly and see it take
  effect on the very next request, with no module reload. `RATE_LIMIT_ENABLED`
  is the one exception (fix round 1, architect-confirmed): slowapi's
  `Limiter.__init__` takes `enabled` as a plain bool, not a callable, so it is
  read from `settings.RATE_LIMIT_ENABLED` exactly once, at import time, when
  `limiter` is constructed - correct for the real deployment (set once per
  process start) but meaning a test must monkeypatch `limiter.enabled`
  directly, not `settings.RATE_LIMIT_ENABLED`, to flip it at runtime.
  `src/api/main.py` sets `app.state.limiter`, adds `SlowAPIMiddleware`,
  and registers a **synchronous** `RateLimitExceeded` handler that returns
  `JSONResponse({"detail": "Too many requests. Please slow down."}, status_code=429)`
  passed through `apply_security_headers`. The handler must be sync, not
  `async def`: slowapi's `SlowAPIMiddleware` enforces `default_limits` by
  calling the matched exception handler synchronously and silently falls back
  to its own generic `{"error": ...}` handler whenever the registered one is a
  coroutine function (read from the installed package this session) - an
  `async` handler here would work for per-route `@limiter.limit(...)`
  rejections (which go through Starlette's normal exception middleware) but
  silently never run for a default-limit rejection on an undecorated route
  like `/health`.
- Per-route limits: `/api/v1/images` (`RATE_LIMIT_IMAGES`, default
  `120/minute`), `/api/v1/builder/slots`, `/validate`, `/candidates`, and
  `GET /builder/builds/{token}` (`RATE_LIMIT_BUILDER`, default `60/minute`),
  and `POST /builder/builds` (`RATE_LIMIT_SAVE_BUILD`, default `10/minute`) -
  each via `@limiter.limit(lambda: settings.RATE_LIMIT_X)`, a callable so the
  limit value is also read live.
- **SEC-04 (image-proxy streaming cap):** `product_image` now uses
  `client.stream("GET", url)` instead of `client.get(...)` + `r.content`. The
  manual per-hop redirect loop is unchanged in spirit (each hop's URL is
  checked against `is_allowed` before it is requested); the final response's
  body is read via `iter_bytes()`, accumulated into a `bytearray`, and the
  route returns the placeholder as soon as the running total exceeds
  `MAX_BYTES` - it never reads the rest of an oversized body.
- **SEC-07 (save-build caps):** `src/api/routes/builder.py` adds
  `cap_body_size(request)` (reads `await request.body()`, raises `413` over
  10,000 bytes; Starlette caches the body so the route's own Pydantic parsing
  still works), attached to `POST /builds` via
  `dependencies=[Depends(cap_body_size)]`. `save_build` raises `400` with
  `"Too many selections (max 20)."` when `len(selections) > 20`, checked
  before the unknown-slot and DB-existence checks (and before any DB query),
  implemented even though only 9 slots exist today.

## Files changed

- `requirements.txt` - `slowapi==0.1.10` pinned with `==`.
- `src/api/rate_limit.py` (new) - `limiter`, `rate_limit_key`.
- `src/api/main.py` - `app.state.limiter`, `SlowAPIMiddleware`, the 429 JSON handler.
- `src/api/routes/images.py` - `@limiter.limit`, streaming 5 MB cap.
- `src/api/routes/builder.py` - `@limiter.limit` on 5 routes, `cap_body_size`, the `>20` check.
- `tests/test_rate_limits.py` (new) - SEC-03 behavior and edge-case coverage.
- `tests/test_image_proxy.py` - SEC-04 streaming/content-type coverage added.
- `tests/test_builder_validation.py` (new) - SEC-07 + builder/save-build rate limits.
- `tests/test_frontend_e2e.py` - `base_url` fixture boots uvicorn with
  `RATE_LIMIT_ENABLED=false`, so hundreds of requests from one Playwright run
  never trip a limit; the limiter itself is exercised by `test_rate_limits.py`.

## Tests

`python -m pytest -q tests --ignore=tests/test_frontend_e2e.py` - 536 passed.
`REQUIRE_E2E=1 python -m pytest -q tests` - see the plan report
(`.superpowers/sdd/phase-01/plan-01-05-report.md`) for the full-suite result.

## Notable design choices (Claude's discretion, flagged)

- `default_limits` is passed to `Limiter` as `[lambda: settings.RATE_LIMIT_DEFAULT]`
  (a callable), not the literal string the plan's Pattern 3 example shows.
  slowapi documents and supports callables in `default_limits`
  (`List[StrOrCallableStr]`, re-evaluated on every request - confirmed by
  reading the installed `slowapi.wrappers.LimitGroup` this session) and this
  is what lets `RATE_LIMIT_DEFAULT` stay test-controllable via a plain
  `monkeypatch.setattr(settings, ...)` with no module reload - simpler and
  more robust than reloading `configs.settings` -> `api.rate_limit` ->
  `api.main` in a particular order for every test. `RATE_LIMIT_ENABLED` is
  different: slowapi's `enabled` constructor parameter is a plain bool, not a
  callable, so it is still read once at import time; tests flip it via
  `monkeypatch.setattr(limiter, "enabled", ...)` instead (fix round 1).
- `RateLimitExceeded`'s handler is a plain function, not `async def` - see the
  explanation above; this is a slowapi-specific pitfall not covered in
  01-RESEARCH.md, found by reading `slowapi.middleware`/`slowapi.extension`
  source directly this session.

## Carry-forwards / concerns

- The default rate-limit numbers (300/min default, 120/min images, 60/min
  builder, 10/min save) are unchanged from 01-01's settings and were not
  re-tuned this plan; 01-RESEARCH.md already flags these as
  Claude's-discretion defaults to revisit once Cloudflare (Phase 3) is caching
  images and real traffic volume is known.
- In-memory limiter storage means the API must stay single-process (already
  documented in `.env.example` by 01-01); this is unchanged and accepted per
  the phase's locked "no Redis" decision.
