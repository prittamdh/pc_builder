"""The switch from server-side scraping to agent jobs (plan 02-05).

With SCRAPE_VIA_AGENTS=true the Airflow scrape task stops fetching store pages and
instead queues due targets for the extensions and returns stuck leases to the queue.
Off (the default), it scrapes as before, so prices keep flowing while the extension is
being tried out.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "dags"))
import scheduled_scraper_dag as dag  # noqa: E402


class _Session:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_agent_mode_queues_and_reaps_without_fetching(monkeypatch):
    from configs import settings

    calls = []
    monkeypatch.setattr(settings, "SCRAPE_VIA_AGENTS", True)
    monkeypatch.setattr(dag, "SessionLocal", _Session)
    monkeypatch.setattr(dag, "reap", lambda s: calls.append("reap") or {"requeued": 0, "failed": 0})
    monkeypatch.setattr(dag, "enqueue_due_targets", lambda s: calls.append("enqueue") or 3)

    def no_fetching(*a, **k):
        raise AssertionError("agent mode must not fetch store pages")

    monkeypatch.setattr(dag, "HttpClient", no_fetching)
    dag.execute_due_scrape_targets()
    assert calls == ["reap", "enqueue"]
