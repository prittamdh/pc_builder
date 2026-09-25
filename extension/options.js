const DEFAULTS = { serverUrl: "", token: "", enabled: true, maxJobs: 10 };
const $ = (id) => document.getElementById(id);

function say(text, ok) {
  $("msg").textContent = text;
  $("msg").className = ok ? "ok" : "bad";
}

async function load() {
  const cfg = await chrome.storage.local.get(DEFAULTS);
  $("serverUrl").value = cfg.serverUrl;
  $("token").value = cfg.token;
  $("maxJobs").value = cfg.maxJobs;
  $("enabled").checked = cfg.enabled;
  await showStatus();
}

async function showStatus() {
  const s = await chrome.storage.local.get(["lastRunAt", "lastSummary", "totals", "lastError"]);
  const rows = [
    ["Last run", s.lastRunAt ? new Date(s.lastRunAt).toLocaleString() : "never"],
    ["Last batch", s.lastSummary ? `${s.lastSummary.leased} pages ${JSON.stringify(s.lastSummary.outcomes)}` : "-"],
    ["All time", s.totals ? JSON.stringify(s.totals) : "-"],
    ["Last error", s.lastError ? `${new Date(s.lastError.at).toLocaleString()}: ${s.lastError.message}` : "none"],
  ];
  $("status").replaceChildren(...rows.map(([k, v]) => {
    const tr = document.createElement("tr");
    for (const text of [k, v]) {
      const td = document.createElement("td");
      td.textContent = text;
      tr.append(td);
    }
    return tr;
  }));
}

$("save").addEventListener("click", async () => {
  let origin;
  try {
    const u = new URL($("serverUrl").value.trim());
    if (u.protocol !== "http:" && u.protocol !== "https:") throw new Error("scheme");
    origin = u.origin;
  } catch {
    return say("The server address should look like http://192.168.1.10:8000", false);
  }
  const token = $("token").value.trim();
  if (!token.startsWith("pcba_")) return say("That is not an agent token (they start with pcba_).", false);
  // Chrome has to allow talking to the server. It asks once per address.
  const granted = await chrome.permissions.request({ origins: [origin + "/*"] });
  if (!granted) return say("Chrome was not allowed to reach that server address.", false);
  const maxJobs = Math.min(50, Math.max(1, parseInt($("maxJobs").value, 10) || 10));
  await chrome.storage.local.set({ serverUrl: origin, token, maxJobs, enabled: $("enabled").checked });
  say("Saved. The next batch starts within a minute.", true);
});

$("test").addEventListener("click", async () => {
  say("Checking...", true);
  const res = await chrome.runtime.sendMessage({ type: "testConnection" });
  if (res.status === 200) say("Connected: the server accepted this token.", true);
  else if (res.status === 401) say("The server refused this token (revoked or mistyped).", false);
  else say(`Could not reach the server (${res.error || "HTTP " + res.status}).`, false);
});

$("run").addEventListener("click", async () => {
  say("Running a batch...", true);
  await chrome.runtime.sendMessage({ type: "runNow" });
  await showStatus();
  say("Batch finished.", true);
});

chrome.storage.onChanged.addListener(showStatus);
load();
