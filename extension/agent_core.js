// Fetch-and-upload logic for the PC Builder price agent. Contract: docs/AGENT_PROTOCOL.md.
//
// Plain ES module with no chrome.* calls, so Node can test it (extension/tests/).
// background.js wires it to the alarm, storage and the badge.

// Must match src/scrapers/store_hosts.py and manifest.json (a Python test checks all three).
export const STORE_DOMAINS = [
  "mdcomputers.in",
  "pcstudio.in",
  "vedantcomputers.com",
  "primeabgb.com",
  "elitehubs.com",
  "shop.clarioncomputers.in",
  "computechstore.in",
  "tpstech.in",
  "modxcomputers.com",
  "tlggaming.com",
];

export const ALLOWED_HEADERS = ["Accept", "X-Requested-With", "HX-Request"];
export const FETCH_TIMEOUT_MS = 20000;
// One character past the server's 5 MB cap: enough for it to store a "body over 5 MB"
// rejection, without sending a 50 MB page it would refuse to read (413).
export const MAX_BODY_CHARS = 5 * 1024 * 1024 + 1;
const MAX_WAIT_MS = 30000;

// Only ever fetch https pages on a store's own domain, whatever the server says.
// A compromised server can't turn the extension on anything else.
export function isStoreUrl(url) {
  let u;
  try {
    u = new URL(url);
  } catch {
    return false;
  }
  if (u.protocol !== "https:") return false;
  const host = u.hostname.toLowerCase();
  return STORE_DOMAINS.some((d) => host === d || host.endsWith("." + d));
}

export function safeHeaders(headers) {
  const out = {};
  for (const [name, value] of Object.entries(headers || {})) {
    if (ALLOWED_HEADERS.includes(name)) out[name] = String(value);
  }
  return out;
}

async function post(fetchFn, serverUrl, token, path, body) {
  const res = await fetchFn(serverUrl.replace(/\/+$/, "") + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  return { status: res.status, data, date: res.headers.get("date") };
}

export async function heartbeat({ serverUrl, token, version, fetchFn }) {
  return post(fetchFn, serverUrl, token, "/api/agent/heartbeat", { extension_version: version });
}

// GET one store page exactly as the job says: no cookies, no cache, only allowed headers.
export async function fetchPage(job, fetchFn, timeoutMs = FETCH_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetchFn(job.url, {
      method: "GET",
      credentials: "omit",
      cache: "no-store",
      redirect: "follow",
      headers: safeHeaders(job.headers),
      signal: controller.signal,
    });
    let body = await res.text();
    if (body.length > MAX_BODY_CHARS) body = body.slice(0, MAX_BODY_CHARS);
    return {
      final_url: res.url || job.url,
      http_status: res.status,
      content_type: res.headers.get("content-type"),
      body,
      error: null,
    };
  } catch (err) {
    const error = err && err.name === "AbortError" ? "timeout" : String((err && err.message) || err).slice(0, 200);
    return { final_url: null, http_status: null, content_type: null, body: null, error };
  } finally {
    clearTimeout(timer);
  }
}

// not_before is naive UTC from the server's clock. offsetMs = server clock - our clock,
// so a machine whose clock is off still waits the right amount.
function waitMs(notBefore, nowMs, offsetMs) {
  const start = Date.parse(notBefore + "Z");
  if (Number.isNaN(start)) return 0;
  return Math.min(Math.max(0, start - (nowMs + offsetMs)), MAX_WAIT_MS);
}

// One alarm's worth of work: lease, fetch each job at its time, upload.
// Returns a summary; never throws.
export async function runBatch({
  serverUrl,
  token,
  maxJobs = 10,
  fetchFn,
  sleep = (ms) => new Promise((r) => setTimeout(r, ms)),
  now = () => Date.now(),
}) {
  const summary = { leased: 0, outcomes: {}, skipped: 0, error: null };
  let lease;
  try {
    lease = await post(fetchFn, serverUrl, token, "/api/agent/lease", { max_jobs: maxJobs });
  } catch (err) {
    summary.error = `server unreachable: ${String((err && err.message) || err).slice(0, 200)}`;
    return summary;
  }
  if (lease.status === 401) {
    summary.error = "token refused (revoked or wrong) - create a new one and paste it in Options";
    return summary;
  }
  if (lease.status !== 200 || !lease.data || !Array.isArray(lease.data.jobs)) {
    summary.error = `lease failed: HTTP ${lease.status}`;
    return summary;
  }

  const serverNow = lease.date ? Date.parse(lease.date) : NaN;
  const offsetMs = Number.isNaN(serverNow) ? 0 : serverNow - now();
  const jobs = [...lease.data.jobs].sort((a, b) => String(a.not_before).localeCompare(String(b.not_before)));
  summary.leased = jobs.length;

  for (const job of jobs) {
    if (!isStoreUrl(job.url)) {
      // Never fetched. Its lease just expires on the server.
      summary.skipped += 1;
      continue;
    }
    const wait = waitMs(job.not_before, now(), offsetMs);
    if (wait > 0) await sleep(wait);

    const page = await fetchPage(job, fetchFn);
    let res;
    try {
      res = await post(fetchFn, serverUrl, token, "/api/agent/result", {
        job_id: job.job_id,
        lease_id: job.lease_id,
        ...page,
      });
    } catch (err) {
      summary.error = `upload failed: ${String((err && err.message) || err).slice(0, 200)}`;
      continue;
    }
    let outcome;
    if (res.status === 200 && res.data) outcome = res.data.status;
    else if (res.status === 409) outcome = "stale";
    else if (res.status === 401) {
      summary.error = "token refused (revoked or wrong) - create a new one and paste it in Options";
      break;
    } else outcome = `http_${res.status}`;
    summary.outcomes[outcome] = (summary.outcomes[outcome] || 0) + 1;
  }
  return summary;
}
