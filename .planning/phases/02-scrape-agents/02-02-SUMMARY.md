# 02-02 Summary: fetch/parse split, upload checks, server-driven pagination

Worked inline, test-first. Requirements: AGENT-06, AGENT-07, AGENT-08, AGENT-09 (save
path now records agent and job).

## What was built

- **`src/scrapers/request_planner.py`**: (store, endpoint/query/path, page) -> (url,
  headers, expects json|html) for every platform. `GenericScraper` now calls it; its
  parsers are unchanged. Checked equal to the old code for every real target, pages
  1-3: 788 requests, 0 differences (before the one deliberate change below).
- **`src/pipeline/scrape_results.py`**: `process_upload`, the callback for
  `job_queue.complete()`. Checks, parses, saves with `agent_id`/`job_id`, queues the
  next page, all in the job's transaction. The order of checks and their outcomes is in
  `docs/AGENT_PROTOCOL.md`.
- **`src/pipeline/scrape_planning.py`**: `enqueue_due_targets` (for the 02-03 worker),
  `enqueue_targets`, `find_unseen_products`, `enqueue_products`.
- **Server-driven pagination**: page N+1 is queued only if page N brought product ids
  no earlier page of the run did; earlier pages are found through the new
  `scrape_jobs.parent_job_id` (migration `c8a4f2e6b193`). Stops at the target's
  `max_pages`, a later empty page, or a later 404.
- **`scripts/repair_unseen_products.py`** queues `product_page` jobs;
  **`scripts/re_scrape_all_stores.py`** queues page 1 of every target. Neither fetches
  store pages any more.
- **`HttpClient` refuses store hosts when `ENV=production`**
  (`scrapers/store_hosts.py`; a test fails if a store in the DB is missing from the list).
  A grep test lists the files still using `HttpClient` and why: the four Phase 4 spec
  scrapers, the Airflow DAG (until 02-03), and the old `src/main.py`.

## Found on real pages (live, 2026-09-25)

- **EliteHubs pages went over 5 MB** at Shopify's 250 per page (motherboards 6.1 MB,
  monitors 5.5 MB). Shopify pages now ask for 100 (`SHOPIFY_PAGE_SIZE`); the largest
  measured is 2.74 MB. All 9 active stores' page 1 pass every check.
- **EliteHubs was already missing products**: its targets had `max_pages: 1`, and
  motherboards and monitors each have 400+ products, so anything past the 250th was
  never seen. Data migration `d5e9b3c7a410` sets its 17 targets to 10 pages. This also
  helps the still-running Airflow scraper.
- Product pages for **PrimeABGB, Clarion and ModxComputers don't parse today** (no
  Product JSON-LD). An old gap, not new: their `product_page` jobs will be `rejected`
  with a parse error until the parser learns their markup.

## Tests

`tests/test_request_planner.py` (10), `tests/test_scrape_results.py` (26),
`tests/test_server_fetch_refusal.py` (10). Upload tests run the real parser on
Shopify JSON fixtures in the throwaway schema.

## For later plans

- 02-03: the worker calls `enqueue_due_targets` and `reap` on a schedule.
- 02-04: `complete(..., process=scrape_results.process_upload)`. The stored outcome
  includes `pids` for pagination, so return only `job_id`, `status`, `reason` to agents.
  The request cap must allow a 5 MB body inside JSON (escaping adds a little).
- 02-05: the extension's `host_permissions` = `scrapers/store_hosts.STORE_DOMAINS`
  (with `www.` / subdomains).
