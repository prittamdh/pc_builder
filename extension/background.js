// Service worker: every minute, lease a small batch of store pages from the PC Builder
// server, fetch them, and upload them (agent_core.js). Settings live in
// chrome.storage.local and are edited on the options page.
import { heartbeat, runBatch } from "./agent_core.js";

const DEFAULTS = { serverUrl: "", token: "", enabled: true, maxJobs: 10 };
const VERSION = chrome.runtime.getManifest().version;

function ensureAlarm() {
  chrome.alarms.get("tick", (alarm) => {
    if (!alarm) chrome.alarms.create("tick", { periodInMinutes: 1 });
  });
}

chrome.runtime.onInstalled.addListener(ensureAlarm);
chrome.runtime.onStartup.addListener(ensureAlarm);
ensureAlarm();

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "tick") tick();
});

chrome.action.onClicked.addListener(() => chrome.runtime.openOptionsPage());

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg && msg.type === "runNow") {
    tick().then(() => reply({ ok: true }));
    return true;
  }
  if (msg && msg.type === "testConnection") {
    chrome.storage.local.get(DEFAULTS).then(async (cfg) => {
      try {
        const res = await heartbeat({ serverUrl: cfg.serverUrl, token: cfg.token, version: VERSION, fetchFn: fetch });
        reply({ status: res.status });
      } catch (err) {
        reply({ status: 0, error: String((err && err.message) || err) });
      }
    });
    return true;
  }
  return false;
});

function badge(text, color) {
  chrome.action.setBadgeText({ text });
  chrome.action.setBadgeBackgroundColor({ color });
}

let running = false;

async function tick() {
  if (running) return; // the last batch is still going
  running = true;
  try {
    const cfg = await chrome.storage.local.get(DEFAULTS);
    if (!cfg.enabled) return badge("OFF", "#6b7280");
    if (!cfg.serverUrl || !cfg.token) return badge("SET", "#d97706");

    const summary = await runBatch({
      serverUrl: cfg.serverUrl,
      token: cfg.token,
      maxJobs: cfg.maxJobs,
      fetchFn: (url, opts) => fetch(url, opts),
    });

    const { totals = {} } = await chrome.storage.local.get("totals");
    for (const [k, v] of Object.entries(summary.outcomes)) totals[k] = (totals[k] || 0) + v;
    await chrome.storage.local.set({
      lastRunAt: new Date().toISOString(),
      lastSummary: summary,
      totals,
      ...(summary.error ? { lastError: { at: new Date().toISOString(), message: summary.error } } : {}),
    });

    if (summary.error) badge("ERR", "#dc2626");
    else if (summary.leased) badge(String(summary.outcomes.done || 0), "#16a34a");
    else badge("", "#16a34a");
  } finally {
    running = false;
  }
}
