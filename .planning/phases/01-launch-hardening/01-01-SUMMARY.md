---
phase: 01-launch-hardening
plan: 01
status: done
---

# Plan 01-01 Summary: Config and header hardening

## What shipped

- **SEC-01 (CORS):** `src/api/main.py` now builds `CORSMiddleware` with
  `allow_origins=settings.CORS_ALLOWED_ORIGINS` (an explicit, comma-separated
  allow-list from the new `CORS_ALLOWED_ORIGINS` env var, empty by default),
  `allow_credentials=False`, `allow_methods=["GET", "POST"]`,
  `allow_headers=["Content-Type"]`. An unlisted `Origin` gets no
  `Access-Control-Allow-Origin` header; a listed one is echoed back exactly;
  credentials are never sent.
- **SEC-02 (DATABASE_URL):** `src/configs/settings.py`'s default credential
  literal is gone (`DATABASE_URL = os.getenv("DATABASE_URL")`, no default).
  `require_database_url()` raises `RuntimeError` naming only `DATABASE_URL`
  (never a connection string) when unset/blank; `src/api/main.py` calls it
  before importing `api.routes` (which would otherwise import `db.connection`
  and fail with an unhelpful `TypeError`).
- **SEC-05 (security headers):** `apply_security_headers()` + an
  `@app.middleware("http")` wrapper set `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: strict-origin-when-cross-origin`, and a
  `Content-Security-Policy` (with `frame-ancestors 'none'`, `'unsafe-inline'`
  kept for `script-src`/`style-src` this phase, and `fonts.googleapis.com`/
  `fonts.gstatic.com` allowed for the site's Google Fonts `@import`) on every
  response. No `Strict-Transport-Security` header is ever sent by the app.
- **SEC-06 (docs off in prod):** `docs_url`/`redoc_url`/`openapi_url` are
  `None` whenever `settings.ENV == "production"`.
- **ENV validation (fix round 1, architect finding):** `ENV` is normalised
  (`.strip().lower()`) and restricted to exactly `"development"` or
  `"production"`; any other value (`"prod"`, `"Production"`'s untrimmed/
  differently-cased typos aside - those normalise correctly - but things like
  `"prod"` or `"staging"`) raises `RuntimeError` at settings-import time,
  naming `ENV` and the two allowed values, so a typo fails closed instead of
  silently leaving `/docs` and `/openapi.json` public.
- **SEC-08 (.env.example):** new `.env.example` at the repo root documents
  every variable read by `src/configs/settings.py` and every `${VAR}` in
  `docker-compose.yml`, all values empty or angle-bracket placeholders.
  `tests/test_env_example.py` cross-checks this by regex/AST-free parsing, so
  a variable added to code or compose without an `.env.example` entry fails
  the suite.
- Also added, for later plans to consume without touching `settings.py`/
  `.env.example` again: `TRUST_CF_CONNECTING_IP`, `RATE_LIMIT_ENABLED`,
  `RATE_LIMIT_DEFAULT`, `RATE_LIMIT_IMAGES`, `RATE_LIMIT_BUILDER`,
  `RATE_LIMIT_SAVE_BUILD` (01-05's limiter), `CONTACT_EMAIL` (01-02's `/about`
  route, empty until the owner picks an address).

## Tests added

`tests/test_cors.py`, `tests/test_docs_disabled.py`, `tests/test_settings.py`,
`tests/test_security_headers.py`, `tests/test_env_example.py`, plus a shared
`tests/conftest.py` fixture (`app_with_env`) used by the CORS/docs tests to
reload `configs.settings`/`api.main` under specific env vars and guarantee
cleanup in fixture teardown (not as the last line of the test body, so a
failed assertion can't leave stale reloaded state for later tests).

## Carry-forwards to later phases (explicitly out of scope here)

- **SEC-08 VM clause -> Phase 3 (`docs/DEPLOY.md`, plan 03-02):** `.env` must
  be mode `600` and owned by the service user on the production VM, with LLM
  keys living only there. This cannot be tested in Phase 1 because no VM
  exists yet; plan 03-02 (`web-dev`, per `ROADMAP.md`) must record this in
  `docs/DEPLOY.md` and verify it as part of the deploy script/checklist.
- **HSTS -> Phase 3 (`Caddyfile`, plan 03-02):** the app itself deliberately
  never sends `Strict-Transport-Security` (Pitfall: it would poison a
  developer's browser on plain HTTP). Plan 03-02's Caddy config is the
  correct place to add it, since Caddy only ever serves the real production
  domain over HTTPS.
- **Production curl check -> Phase 3 (plan 03-02):** the literal "curl the
  production URL and confirm the security headers/HSTS are present" check
  from SEC-05's research can't run until a production host exists. Plan
  03-02's health-check/deploy verification step should include it.

## Follow-on plans that depend on this one

- **01-02** reuses `apply_security_headers()` on its new 500 handler
  (Starlette's server-error layer sits outside user middleware) and reads
  `settings.CONTACT_EMAIL` for the `/about` route.
- **01-05** reads `settings.TRUST_CF_CONNECTING_IP` and the `RATE_LIMIT_*`
  strings to build its `slowapi` limiter.
