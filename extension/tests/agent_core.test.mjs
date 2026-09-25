// Run: node --test extension/tests/   (also run by tests/test_extension.py)
import test from "node:test";
import assert from "node:assert/strict";

import { fetchPage, isStoreUrl, MAX_BODY_CHARS, runBatch, safeHeaders } from "../agent_core.js";

function response({ status = 200, body = "", url = "", headers = {} } = {}) {
  const h = new Map(Object.entries(headers).map(([k, v]) => [k.toLowerCase(), v]));
  return {
    status,
    url,
    headers: { get: (k) => h.get(k.toLowerCase()) ?? null },
    text: async () => body,
    json: async () => JSON.parse(body),
  };
}

// A fake world: the agent server plus store pages, recording every request.
function world({ jobs = [], pages = {}, leaseStatus = 200, resultStatus = 200, serverDate = null }) {
  const calls = [];
  const fetchFn = async (url, opts = {}) => {
    calls.push({ url, opts });
    if (url.endsWith("/api/agent/lease")) {
      return response({
        status: leaseStatus,
        body: JSON.stringify({ jobs }),
        headers: serverDate ? { date: serverDate } : {},
      });
    }
    if (url.endsWith("/api/agent/result")) {
      const sent = JSON.parse(opts.body);
      return response({ status: resultStatus, body: JSON.stringify({ job_id: sent.job_id, status: "done", reason: null }) });
    }
    const page = pages[url];
    if (page instanceof Error) throw page;
    return response({ status: 200, url, body: page ?? "<html></html>", headers: { "content-type": "text/html" } });
  };
  return { calls, fetchFn };
}

const job = (id, url, extra = {}) => ({
  job_id: id, lease_id: `L${id}`, url, headers: {}, store_host: new URL(url).hostname,
  not_before: "2026-10-01T12:00:00", ...extra,
});
const at = (iso) => () => Date.parse(iso + "Z");

test("only https URLs on a store domain are allowed", () => {
  assert.ok(isStoreUrl("https://mdcomputers.in/catalog/processor"));
  assert.ok(isStoreUrl("https://www.vedantcomputers.com/x"));
  assert.ok(!isStoreUrl("http://mdcomputers.in/"));
  assert.ok(!isStoreUrl("https://mdcomputers.in.evil.example/"));
  assert.ok(!isStoreUrl("https://notmdcomputers.in/"));
  assert.ok(!isStoreUrl("https://192.168.1.1/"));
  assert.ok(!isStoreUrl("not a url"));
});

test("only allowlisted headers are passed on", () => {
  assert.deepEqual(safeHeaders({ Accept: "a", Cookie: "x", "HX-Request": "true", Authorization: "y" }),
    { Accept: "a", "HX-Request": "true" });
});

test("a batch fetches each job without cookies and uploads what came back", async () => {
  const w = world({
    jobs: [job(1, "https://mdcomputers.in/a", { headers: { Accept: "text/html", Cookie: "no" } })],
    pages: { "https://mdcomputers.in/a": "<html>page</html>" },
  });
  const summary = await runBatch({
    serverUrl: "http://server:8000/", token: "pcba_t", fetchFn: w.fetchFn,
    sleep: async () => {}, now: at("2026-10-01T12:00:00"),
  });
  assert.equal(summary.leased, 1);
  assert.deepEqual(summary.outcomes, { done: 1 });
  assert.equal(summary.error, null);

  const [lease, page, result] = w.calls;
  assert.equal(lease.url, "http://server:8000/api/agent/lease");
  assert.equal(lease.opts.headers.Authorization, "Bearer pcba_t");
  assert.equal(page.opts.credentials, "omit");
  assert.equal(page.opts.cache, "no-store");
  assert.deepEqual(page.opts.headers, { Accept: "text/html" });
  const sent = JSON.parse(result.opts.body);
  assert.deepEqual(
    { job_id: sent.job_id, lease_id: sent.lease_id, final_url: sent.final_url, http_status: sent.http_status,
      content_type: sent.content_type, body: sent.body, error: sent.error },
    { job_id: 1, lease_id: "L1", final_url: "https://mdcomputers.in/a", http_status: 200,
      content_type: "text/html", body: "<html>page</html>", error: null },
  );
});

test("a job off the store list is never fetched", async () => {
  const w = world({ jobs: [job(1, "https://evil.example/x"), job(2, "http://10.0.0.1/")] });
  const summary = await runBatch({ serverUrl: "http://s", token: "t", fetchFn: w.fetchFn, sleep: async () => {} });
  assert.equal(summary.skipped, 2);
  assert.deepEqual(w.calls.map((c) => c.url), ["http://s/api/agent/lease"]);
});

test("jobs wait for not_before, measured on the server's clock", async () => {
  const waits = [];
  const w = world({
    jobs: [job(2, "https://mdcomputers.in/b", { not_before: "2026-10-01T12:00:20" }),
           job(1, "https://mdcomputers.in/a", { not_before: "2026-10-01T12:00:10" })],
    // our clock reads 11:59:55 but the server says 12:00:00 - we are 5 s behind
    serverDate: "Thu, 01 Oct 2026 12:00:00 GMT",
  });
  let clock = Date.parse("2026-10-01T11:59:55Z");
  await runBatch({
    serverUrl: "http://s", token: "t", fetchFn: w.fetchFn,
    sleep: async (ms) => { waits.push(ms); clock += ms; }, now: () => clock,
  });
  assert.deepEqual(waits, [10000, 10000]);
  const fetched = w.calls.filter((c) => c.url.startsWith("https://")).map((c) => c.url);
  assert.deepEqual(fetched, ["https://mdcomputers.in/a", "https://mdcomputers.in/b"]);
});

test("a failed fetch is reported as an error so the server retries it", async () => {
  const w = world({ jobs: [job(1, "https://mdcomputers.in/a")], pages: { "https://mdcomputers.in/a": new Error("net down") } });
  await runBatch({ serverUrl: "http://s", token: "t", fetchFn: w.fetchFn, sleep: async () => {} });
  const sent = JSON.parse(w.calls.at(-1).opts.body);
  assert.equal(sent.http_status, null);
  assert.equal(sent.body, null);
  assert.equal(sent.error, "net down");
});

test("a huge page is cut just past the 5 MB cap so the server can record why", async () => {
  const big = "x".repeat(MAX_BODY_CHARS + 1000);
  const page = await fetchPage(job(1, "https://mdcomputers.in/a"), async (url) => response({ url, body: big }));
  assert.equal(page.body.length, MAX_BODY_CHARS);
});

test("a refused token stops the batch with a clear error", async () => {
  const w = world({ leaseStatus: 401 });
  const summary = await runBatch({ serverUrl: "http://s", token: "t", fetchFn: w.fetchFn });
  assert.match(summary.error, /token refused/);
});

test("a stale lease is counted, not retried", async () => {
  const w = world({ jobs: [job(1, "https://mdcomputers.in/a")], resultStatus: 409 });
  const summary = await runBatch({ serverUrl: "http://s", token: "t", fetchFn: w.fetchFn, sleep: async () => {} });
  assert.deepEqual(summary.outcomes, { stale: 1 });
});

test("an unreachable server is an error, not a crash", async () => {
  const summary = await runBatch({
    serverUrl: "http://s", token: "t", fetchFn: async () => { throw new Error("ECONNREFUSED"); },
  });
  assert.match(summary.error, /server unreachable/);
});
