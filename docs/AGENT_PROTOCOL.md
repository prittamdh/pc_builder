# Scrape agent protocol

How the browser extension (the "agent") and the server talk. Plan 02-01 owns this
contract. The server side of the queue is `src/pipeline/job_queue.py`, the endpoints
are plan 02-04, and the extension is plan 02-05.

In short: the server decides what to fetch and when. The agent fetches the page exactly
as told and uploads what it got. The server checks it, parses it and saves the prices.

## Auth

Every request carries `Authorization: Bearer <token>`.

- The owner makes one token per install: `python scripts/agent_tokens.py create --name laptop`.
  It is printed once and stored only as a SHA-256 hash. Lost token: create a new one.
- `python scripts/agent_tokens.py revoke --name laptop` takes effect on that agent's next request.
- No token, an unknown token, or a revoked token gets **401**.
- Requests are rate-limited per token. Too many gets **429** with `Retry-After`.
- The endpoints are left out of the public OpenAPI schema.

All bodies are JSON. Times are UTC, ISO 8601, without an offset (`2026-10-01T12:00:10`).

## `POST /api/agent/lease`

Ask for work. Also counts as a check-in.

Request:

```json
{ "max_jobs": 10 }
```

`max_jobs` is capped at 50. Response **200**:

```json
{
  "jobs": [
    {
      "job_id": 812,
      "lease_id": "5f0c1c1e-2b7a-4c55-9f1e-0e6f9f5a3c11",
      "url": "https://mdcomputers.in/catalog/processor?page=2",
      "headers": { "Accept": "text/html" },
      "store_host": "mdcomputers.in",
      "not_before": "2026-10-01T12:00:10"
    }
  ]
}
```

An empty `jobs` list means nothing is due; ask again at the next alarm.

What the server guarantees:

- A job is leased to one agent at a time (row locks with `SKIP LOCKED`).
- **Pacing.** Each store has a minimum gap between fetches (`stores.min_fetch_interval_s`,
  10 s by default). It is shared by every agent, because the agents may all sit behind
  one home IP. Jobs for the same store come with `not_before` times at least that gap
  apart, across all agents together.
- A lease only covers fetches due within the next 25 seconds, so a batch fits inside one
  service-worker wake-up.
- `headers` only ever contains `Accept`, `X-Requested-With` or `HX-Request`.
- `url` is always `https` on the store's own domain.

## Fetching (the agent's rules)

- Don't start a job before its `not_before`. Fetch a batch's jobs one after another in
  `not_before` order.
- `fetch(url, { credentials: "omit", cache: "no-store", redirect: "follow", headers })`.
  No cookies, no logins, only the headers the job gives.
- Refuse any `url` whose host isn't one of the store hosts in the extension's manifest,
  even if the server sent it. A compromised server can't turn the extension on anything else.
- Never try to solve or get around a bot check or captcha. Upload what came back; the
  server marks it `blocked`.
- Upload within **120 seconds after `not_before`**. After that the lease expires and the
  job goes to another agent.

## `POST /api/agent/result`

Upload one fetch. Send this for failed fetches too, so the job is retried soon instead of
waiting for its lease to expire.

Request:

```json
{
  "job_id": 812,
  "lease_id": "5f0c1c1e-2b7a-4c55-9f1e-0e6f9f5a3c11",
  "final_url": "https://mdcomputers.in/catalog/processor?page=2",
  "http_status": 200,
  "content_type": "text/html; charset=utf-8",
  "body": "<!DOCTYPE html>...",
  "error": null
}
```

- `final_url` is `response.url`, after redirects.
- `body` is `await response.text()`, at most **5 MB**. A bigger request is refused with **413**.
- If `fetch()` itself threw (network error, timeout), send `http_status: null`,
  `body: null` and a short `error` such as `"timeout"`.

Response **200**:

```json
{ "job_id": 812, "status": "done", "reason": null }
```

| `status`   | Meaning |
|------------|---------|
| `done`     | Parsed and saved. |
| `requeued` | The fetch failed (network error, 5xx, 429...). The job will be retried later, maybe by another agent. |
| `failed`   | Failed on its last allowed attempt (3), or unusable for good. Counted in health. |
| `blocked`  | The store answered with a challenge, login or captcha page. Nothing saved. |
| `rejected` | The upload failed a check (below). Nothing saved. |

Sending the same `(job_id, lease_id)` again returns the same response and saves nothing
new, so it is safe to retry an upload after a network error.

Other responses: **409** if the lease isn't current (it expired and was handed out
again, or belongs to another agent; nothing is saved, drop the job), **400** for a
malformed request, **401**, **413**, **429** as above.

### What the server checks before saving (plan 02-02)

The server trusts an upload less than its own fetches. `src/pipeline/scrape_results.py`
runs these checks in this order, and stores the outcome and reason on the job:

| Upload | Outcome |
|--------|---------|
| `error` set, or no `http_status` | `requeued` (or `failed` on the 3rd attempt) |
| body over 5 MB | `rejected` |
| `final_url` not on the store's domain | `rejected` |
| a Cloudflare challenge page (markers in `generic_scraper._is_challenge_body`), or redirected to a login page | `blocked` |
| HTTP 429 or 5xx | `requeued` |
| HTTP 401 or 403 | `blocked` |
| HTTP 404/410 on a listing | page 1: `failed`; a later page: `done`, the listing ends there |
| HTTP 404/410 on a product page | `done`, the product is marked out of stock |
| any other non-2xx | `failed` |
| content type isn't what the store's platform serves (JSON or HTML) | `rejected` |
| the parser raises | `rejected` |
| listing page 1 parses to 0 products | `failed`, never a quiet "empty" |

A price of 0 or above ₹20,00,000 is a parse error, not a price: that item is dropped
and counted (`dropped_prices`), and the rest of the page is saved.

Shopify listings are asked for 100 products a page, so even EliteHubs' biggest pages
stay near 2.5 MB (at 250 a page they reached 6 MB).

## `POST /api/agent/heartbeat`

Optional check-in when the agent has nothing to lease (a lease call already counts).

```json
{ "extension_version": "0.1.0" }
```

Response **200** `{ "ok": true }`. `/health/pipeline` goes to 503 when no agent has
checked in for 24 hours.

## Job life cycle (server side)

```
queued --lease--> leased --result--> done | blocked | rejected | failed
                    |                  \--(fetch failed)--> queued, with backoff
                    \--lease expired--> queued, with backoff (failed after 3 leases)
```

- Each lease counts as one attempt. After 3, the job is `failed`.
- Backoff before a retry: 60 s after the first failed attempt, 120 s after the second.
- A page is queued at most once while it is waiting or being fetched. Once a job is
  finished, the next cycle can queue the same page again.
- Pagination is decided by the server: page N+1 is queued only if page N brought new
  product ids (plan 02-02).
- Every saved price records `agent_id` and `job_id`, so one agent's data can be found
  and removed after a revoke.
