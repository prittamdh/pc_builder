# PC Builder Price Agent (Chrome extension)

Install this on any computer with Chrome. Every minute it asks the PC Builder server
for a few store pages, fetches them, and sends them back. The server reads the prices
and saves them. Several computers can run it at once; the server shares the work out
and keeps each store's pace gentle across all of them.

It sends **no cookies**, never logs in anywhere, and only ever opens pages on the 10
store sites listed in `manifest.json`, whatever the server asks.

## 1. Let other computers reach the server

On the PC that runs the PC Builder API, start it listening on the home network, not
just on itself:

```
python -m uvicorn api.main:app --app-dir src --host 0.0.0.0 --port 8000
```

Find that PC's address (`ipconfig`, the "IPv4 Address", e.g. `192.168.1.10`).
The first time, Windows may ask whether Python can accept connections: allow it for
**private** networks only.

Only the computer running the server needs this. The extension on that same computer
can use `http://localhost:8000`.

## 2. Make a token for each computer

On the server PC, once per computer (use a name you'll recognise):

```
python scripts/agent_tokens.py create --name laptop
```

Copy the `pcba_...` token it prints. It is shown only once.

- `python scripts/agent_tokens.py list` shows every agent and when it last checked in.
- `python scripts/agent_tokens.py revoke --name laptop` cuts one off at once.

## 3. Install the extension

1. Copy this `extension` folder to the computer (or use the repo if it's there).
2. Open `chrome://extensions`, turn on **Developer mode** (top right).
3. Click **Load unpacked** and pick the `extension` folder.
4. Click the extension's icon (pin it from the puzzle-piece menu first). The options
   page opens.
5. Fill in the **server address** (e.g. `http://192.168.1.10:8000`) and the **token**,
   then **Save**. Chrome asks once to allow that server address; allow it.
6. **Test connection** should say "Connected". **Run now** runs one batch straight away.

## 4. Give it work

The extensions only fetch pages the server has queued. Either:

- **Try one store:** `python scripts/re_scrape_all_stores.py elitehubs` queues page 1 of
  each of its categories. The server queues the next pages itself while they keep
  bringing new products.
- **Switch over fully:** set `SCRAPE_VIA_AGENTS=true` in `.env` and restart Airflow. The
  15-minute scrape task then queues due targets for the extensions instead of fetching
  pages itself.

## The badge

| Badge | Meaning |
|-------|---------|
| a number | pages saved in the last batch |
| blank | nothing was due |
| `SET` | server address or token missing |
| `OFF` | turned off in Options |
| `ERR` | the last batch hit a problem; Options shows it |

Chrome must be open for the extension to run. If you close Chrome in the middle of a
batch nothing is lost: the unfinished pages go back in the queue after 2 minutes and
another computer picks them up.

## Updating

After changing files here, click the reload icon on the extension's card in
`chrome://extensions`. Settings are kept.

## For developers

- `agent_core.js` has all the fetch/upload logic and no `chrome.*` calls:
  `node --test extension/tests/agent_core.test.mjs`.
- `tests/test_extension_e2e.py` loads the extension in Playwright's Chromium against the
  real API and a fixture store page.
- The store list lives in three places that a test keeps equal:
  `src/scrapers/store_hosts.py`, `manifest.json` and `agent_core.js`.
- The protocol is `docs/AGENT_PROTOCOL.md`.
