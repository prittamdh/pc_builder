---
phase: "1"
slug: "launch-hardening"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-24"
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `01-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4+, Playwright sync API for e2e |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `testpaths = ["tests"]`) |
| **Quick run command** | `python -m pytest -q tests --ignore=tests/test_frontend_e2e.py` |
| **Full suite command** | `python -m pytest -q tests` |
| **Estimated runtime** | ~10 seconds quick; ~360 seconds full (Playwright) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest -q tests --ignore=tests/test_frontend_e2e.py`
- **After every plan wave:** Run `python -m pytest -q tests`
- **Before `/gsd:verify-work`:** Full suite must be green, with zero Playwright skips (WEB-03)
- **Max feedback latency:** 10 seconds (quick suite)

---

## Per-Task Verification Map

Task IDs are filled in once PLAN.md files exist; rows are keyed by plan and requirement.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-01-* | 01 | 1 | SEC-01 | T-1-* | Unlisted Origin gets no `Access-Control-Allow-Origin` | unit | `python -m pytest -q tests/test_cors.py` | ❌ W0 | ⬜ pending |
| 1-01-* | 01 | 1 | SEC-02 | T-1-* | App refuses to start without `DATABASE_URL`; no default credentials in `src/` | unit + grep | `python -m pytest -q tests/test_settings.py` | ❌ W0 | ⬜ pending |
| 1-01-* | 01 | 1 | SEC-03 | T-1-* | Over-limit requests get 429 keyed on the real client IP | unit | `python -m pytest -q tests/test_rate_limits.py` | ❌ W0 | ⬜ pending |
| 1-01-* | 01 | 1 | SEC-04 | T-1-* | Oversized or non-image upstream gives the placeholder | unit | `python -m pytest -q tests/test_image_proxy.py` | ✅ extend | ⬜ pending |
| 1-01-* | 01 | 1 | SEC-05 | T-1-* | Security headers on HTML; CSP has `frame-ancestors 'none'` | unit | `python -m pytest -q tests/test_security_headers.py` | ❌ W0 | ⬜ pending |
| 1-01-* | 01 | 1 | SEC-06 | T-1-* | `/docs`, `/redoc`, `/openapi.json` 404 in production | unit | `python -m pytest -q tests/test_docs_disabled.py` | ❌ W0 | ⬜ pending |
| 1-01-* | 01 | 1 | SEC-07 | T-1-* | >20 ids, unknown ids, >10KB body all rejected | unit | `python -m pytest -q tests/test_builder_validation.py` | ❌ W0 | ⬜ pending |
| 1-01-* | 01 | 1 | SEC-08 | — | `.env.example` covers every settings/compose variable | unit | `python -m pytest -q tests/test_env_example.py` | ❌ W0 | ⬜ pending |
| 1-02-* | 02 | 2 | WEB-01, WEB-02 | T-1-* | Branded HTML 404; JSON 404 for `/api/*`; 500 without traceback | unit | `python -m pytest -q tests/test_error_pages.py` | ❌ W0 | ⬜ pending |
| 1-02-* | 02 | 2 | WEB-03 | — | Full Playwright suite passes; a skip counts as a failure | e2e | `python -m pytest -q tests/test_frontend_e2e.py` | ✅ | ⬜ pending |
| 1-02-* | 02 | 2 | WEB-04 | — | 375px flow: search → picker → add → verdict → compare | e2e | `python -m pytest -q tests/test_frontend_e2e.py -k mobile` | ✅ extend | ⬜ pending |
| 1-02-* | 02 | 2 | WEB-05 | — | Footer links to About/Privacy with the required disclosures | e2e | `python -m pytest -q tests/test_frontend_e2e.py -k footer` | ✅ extend | ⬜ pending |
| 1-02-* | 02 | 2 | SEO-01 | — | Title/meta/OG/canonical present; `robots.txt` and `sitemap.xml` return 200 | unit | `python -m pytest -q tests/test_seo_basics.py` | ❌ W0 | ⬜ pending |
| 1-03-* | 03 | 3 | FIT-01 | — | Missing input gives `unverified`, naming the part and the spec (one test per rule) | unit | `python -m pytest -q tests/test_compatibility_rules.py` | ✅ extend | ⬜ pending |
| 1-03-* | 03 | 3 | FIT-02 | — | Exactly 3 verdict states; "All checks passed" never shown while anything is unverified | unit + e2e | `python -m pytest -q tests/test_compatibility_rules.py tests/test_frontend_e2e.py` | ✅ extend | ⬜ pending |
| 1-03-* | 03 | 3 | FIT-03 | — | A default TDP names the part and flags the estimate | unit | `python -m pytest -q tests/test_compatibility_rules.py` | ✅ extend | ⬜ pending |
| 1-04-* | 04 | 1 | OPS-05 | — | Per-store staleness names the store | unit | `python -m pytest -q tests/test_price_freshness.py` | ✅ extend | ⬜ pending |
| 1-04-* | 04 | 1 | OPS-06 | — | 0 extractions with a backlog > 0 fails loudly | unit | `python -m pytest -q tests/test_price_freshness.py` | ✅ extend | ⬜ pending |
| 1-04-* | 04 | 1 | AI-01 | — | Offline scoring is exact; the script writes nothing to the DB | unit | `python -m pytest -q tests/test_benchmark_provider.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_cors.py` (SEC-01)
- [ ] `tests/test_settings.py` (SEC-02)
- [ ] `tests/test_rate_limits.py` (SEC-03)
- [ ] `tests/test_security_headers.py` (SEC-05)
- [ ] `tests/test_docs_disabled.py` (SEC-06)
- [ ] `tests/test_builder_validation.py` (SEC-07)
- [ ] `tests/test_env_example.py` (SEC-08)
- [ ] `tests/test_error_pages.py` (WEB-01, WEB-02)
- [ ] `tests/test_seo_basics.py` (SEO-01)
- [ ] `tests/test_benchmark_provider.py` (AI-01)
- [ ] `pip install slowapi`, pinned in `requirements.txt` (verify the package before install)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| DB size and growth report | OPS-07 | Read-only script against the live DB; its output is a measurement, not a pass/fail | `python scripts/measure_db_growth.py`, then confirm it prints table sizes and the snapshot growth rate, and writes nothing |
| Live provider benchmark 8/8 | AI-01 | Makes real calls to mistral and google | `python scripts/benchmark_provider.py --provider mistral` and `--provider google`; both print 8/8 |
| Unverified case shown in the real UI | FIT-02 | Visual wording check in the browser | Build with a case that has no GPU clearance, then confirm the page reads "No problems found - 1 check unverified" and names the case and the spec |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
