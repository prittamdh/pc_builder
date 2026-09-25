---
phase: 01-launch-hardening
plan: 02
status: done
---

# Plan 01-02 Summary: Error pages, SEO basics, About/Privacy

## What shipped

- **WEB-01/WEB-02 (branded 404, generic 500):** `src/api/main.py` gained two
  exception handlers. `branded_404` (registered on `StarletteHTTPException`)
  returns `FileResponse(static_dir / "404.html", status_code=404)` for any
  404 on a path not starting with `/api/`, and otherwise delegates to
  FastAPI's own `http_exception_handler` (unchanged JSON behavior for
  `/api/*` and every other status code - already worked before this plan).
  `branded_500` (registered on the base `Exception`) logs the exception via
  `common.logger.get_logger(__name__).exception(...)` and returns
  `{"detail": "Internal server error."}` JSON for `/api/*` paths or
  `500.html` otherwise; neither body ever contains the exception message, a
  traceback, a `File "..."` line, or the strings `starlette`/`fastapi`. Both
  handlers pass their response through 01-01's `apply_security_headers()`
  since Starlette's server-error layer sits outside the app's own
  middleware stack. `src/static/404.html` and `500.html` are small
  self-contained pages (same head/stylesheet shape as `index.html`, no
  `<script>` tags, 500.html has zero dynamic content).
- **SEO-01 (head tags, favicon, robots.txt, sitemap.xml):** `index.html`'s
  `<head>` gained `meta name="description"`, `og:title`/`og:description`/
  `og:type`, `link rel="icon" href="/static/favicon.svg"`, and
  `link rel="canonical" href="/"` (relative - no production domain exists
  yet). New `src/static/favicon.svg` is a small inline SVG with no external
  references. `main.py` adds `GET /robots.txt` (plain text,
  `User-agent: *` / `Allow: /` / `Disallow: /api/` / an absolute
  `Sitemap:` URL built from `request.base_url`) and `GET /sitemap.xml`
  (a sitemaps.org 0.9 `urlset` with absolute `<loc>` entries for `/`,
  `/about`, `/privacy`).
  **Carry-forward to Phase 3 (plan 03-02):** the canonical link and sitemap
  base are relative/request-derived until a real domain and reverse proxy
  exist; 03-02 must set an absolute canonical + `og:url` and turn on
  uvicorn's `--proxy-headers`/`--forwarded-allow-ips` so `request.base_url`
  reports the real scheme/host behind Caddy/Cloudflare.
- **WEB-05 (About/Privacy, footer links, contact placeholder):** new
  `src/static/about.html` and `privacy.html` (same head shape as the rest
  of the site). About covers: prices collected automatically and may lag;
  not affiliated with any retailer; verify price/stock/specs before buying;
  what an "unverified" compatibility item means; and a "For retailers"
  section containing the literal token `{{CONTACT}}` exactly once. Privacy
  was written only after grepping `app.js` for `localStorage`/
  `sessionStorage`/`document.cookie` (none found) and reading `builder.py`'s
  `save_build` (stores only selections/name/notes under a random share
  token): it states no accounts, what a saved build stores, no browser
  storage, that Google Fonts sees the visitor's IP, that images are
  proxied, standard server logs only, no analytics/trackers, and no price
  alerts/email sign-ups (owner decision). `main.py`'s `GET /about` reads
  `settings.CONTACT_EMAIL` at request time (not import time) and replaces
  `{{CONTACT}}` with an `html.escape`d `mailto:` link when set, or "a
  dedicated contact address for retailers is coming soon." when empty -
  never a hardcoded address. `GET /privacy` serves `privacy.html` directly.
  `index.html`'s footer gained a `<nav class="footer-links">` with
  `href="/about"` and `href="/privacy"`; both new pages link back to `/`
  and to each other.

## Tests added

`tests/test_error_pages.py` (6 tests: branded 404 HTML, JSON 404 for
`/api/*`, JSON 404 for an unknown share token via a `get_db` dependency
override that never touches a real DB, a page-route crash -> 500 HTML with
no leaked internals, an `/api/` route crash -> 500 JSON, and security
headers present on the 404 response), `tests/test_seo_basics.py` (7 tests:
title/description/OG tags, favicon link + file, canonical link,
`robots.txt`, `sitemap.xml` parsed with `xml.etree` and checked for
absolute `<loc>` values), `tests/test_static_pages.py` (7 tests: footer
links, About's required disclosure phrases, contact-empty "coming soon"
with no `@` and no leftover `{{CONTACT}}` token, contact-set `mailto:` link,
HTML-escaping of a markup-bearing `CONTACT_EMAIL`, Privacy mentioning saved
builds and Google Fonts, and both pages cross-linking).

## Verification

- `python -m pytest -q tests/test_error_pages.py tests/test_seo_basics.py tests/test_static_pages.py`
  - 20 passed.
- `python -m pytest -q tests --ignore=tests/test_frontend_e2e.py` - 1 failed
  (`tests/test_benchmark_provider.py::test_source_has_no_identity_prompt_reference_and_no_bare_key_flag`),
  414 passed. That failure is in a data-engineer-owned file being edited
  concurrently in this same working tree (`scripts/benchmark_provider.py`,
  `tests/test_benchmark_provider.py` both show as modified in `git status`
  at the start of this session) - unrelated to this plan's files.
- `python -m pytest -q tests/test_frontend_e2e.py -k "TestPageLoads or footer"` -
  4 passed, 0 skipped.
- `python -m pytest -q tests/test_frontend_e2e.py` (full suite) - 46 passed,
  5 failed. **Pre-existing, not caused by this plan** (see Concerns below).
- Manual browser check (uvicorn on a scratch port): `/`, `/about`,
  `/privacy`, `/robots.txt`, `/sitemap.xml` all 200; `/no-such-page` 404
  branded HTML. Checked `/`, `/no-such-page`, `/about` at an explicit
  375x812 viewport and at the pane's default (desktop) width - no console
  errors on any of these loads (the console did show `Failed to load
  resource: 404` entries, but those are the browser's own note about the
  `/no-such-page` navigation returning 404, not a script error). Confirmed
  via `read_network_requests` that a normal `/` load's outbound requests are
  all 200 OK.

## Concerns / carry-forwards

- **Pre-existing CSP regression, not introduced by this plan:** the full
  `tests/test_frontend_e2e.py` run has 5 failures, all
  `playwright._impl._errors.Error: Page.wait_for_function: EvalError:
  Evaluating a string as JavaScript violates ... 'unsafe-eval' is not an
  allowed source of script: script-src 'self' 'unsafe-inline'`. This is
  01-01's `_CSP` (`script-src 'self' 'unsafe-inline'`, no `'unsafe-eval'`)
  colliding with Playwright's `page.wait_for_function("...")` (a string
  argument gets `eval`'d inside the page). This plan's diff never touches
  `_CSP` or any test that uses `wait_for_function` - confirmed via
  `git diff src/api/main.py`, which only adds the two exception handlers,
  `/about`, `/privacy`, `/robots.txt`, `/sitemap.xml`. This should be
  flagged to whoever owns 01-01/CSP follow-up: either loosen the CSP with
  `'unsafe-eval'` (a real weakening, not recommended) or rewrite the 5
  affected tests to use a `page.wait_for_function(lambda_equivalent)`-free
  approach (e.g. polling `page.locator(...).count()` in a Python loop
  instead of a JS string). Not fixed here - out of this plan's scope
  (01-02's task list never mentions the CSP) and touches a header owned by
  a different, already-reviewed plan.
- `tests/test_benchmark_provider.py` failure noted above is data-engineer's
  concurrent work in progress, not this plan's responsibility - re-run
  `tests --ignore=tests/test_frontend_e2e.py` once that file settles.

## Follow-on plans that depend on this one

- **03-02** must make the canonical link, `og:url`, and the sitemap's
  `<loc>` base absolute, and add uvicorn's proxy-header flags so
  `request.base_url` reports the real production host/scheme.
- Whoever picks a `CONTACT_EMAIL` value only needs to set the env var and
  restart - `/about` reads it at request time, no code change needed.
