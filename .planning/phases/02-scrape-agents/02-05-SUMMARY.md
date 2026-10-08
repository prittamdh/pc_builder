# 02-05 Summary: the Chrome extension

Worked inline, test-first for the logic. Done before 02-03 at the owner's request
(2026-09-25). Requirement: AGENT-10.

## What was built (`extension/`)

- **`manifest.json`**: MV3, permissions `alarms` and `storage` only. Host permissions:
  the 10 store domains (and their subdomains) plus localhost. The server's address on
  the home network is asked for at runtime (`optional_host_permissions`), once, when
  the owner saves it on the options page.
- **`agent_core.js`**: all the logic, no `chrome.*` calls: lease, wait for each
  `not_before` (measured on the server's clock via the `Date` header, so a machine with
  a wrong clock still paces right), fetch with `credentials: "omit"` and
  `cache: "no-store"` and only allowlisted headers, upload, count outcomes. Refuses any
  URL that isn't https on a store domain. A failed fetch is uploaded as an error so the
  server retries soon. A page over 5 MB is cut just past the cap so the server can
  record why.
- **`background.js`**: 1-minute alarm, one batch at a time, badge (count / blank /
  `SET` / `OFF` / `ERR`), stats in storage, "Run now" and "Test connection" messages.
- **`options.html` / `options.js`**: server address, token, batch size, on/off, status.
- **`README.md`**: running the API on the home network, tokens, loading unpacked, giving
  it work, the badge.

## Switching over

`SCRAPE_VIA_AGENTS=true` (new setting, default false) makes the Airflow scrape task
reap expired leases and queue due targets instead of fetching pages itself. Until it is
set, Airflow scrapes as before, so prices never stop while the extensions are tried.

## Tests

- `extension/tests/agent_core.test.mjs` (10, Node), run from `tests/test_extension.py`,
  which also checks the manifest and that the store list is identical in
  `store_hosts.py`, `manifest.json` and `agent_core.js`.
- `tests/test_extension_e2e.py`: Playwright's Chromium with the unpacked extension, the
  real API (uvicorn thread, throwaway schema), a fixture store page answered by
  Playwright. "Test connection" and "Run now" on the options page; asserts the page was
  fetched without cookies and both prices saved with the agent's id.
- `tests/test_scrape_via_agents.py`: agent mode queues and reaps, and never fetches.

## Live trial (2026-09-25, real data)

Extension in Chromium -> local API on :8000 -> real EliteHubs processor pages. Four
batches: pages 1-3 saved 50 + 3 + 21 prices (the other new listings were out of stock
and not yet in the catalog, which save() skips as before); page 4 came back empty and
ended the listing. 74 price rows carry the trial agent's id. The `claude-trial` token
was revoked afterwards.

## Still open

- 02-03 (the worker) replaces Airflow's part; until then agent mode lives in the DAG.
- Success criterion 1 (all 10 stores fresh for 48 h on 2+ machines) needs the owner's
  installs.
