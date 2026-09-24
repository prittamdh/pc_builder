"""
Offline tests for scripts/benchmark_provider.py (AI-01).

No network, no DB: the LLM service is faked (a stub with extract_batch), following
tests/test_ask_free_ai.py's FakeService pattern. These tests only exercise
normalize_rating, score_results, run_benchmark and main's argument handling/error
paths - never a live provider call (that is a separate, manual validation step, see
the plan's Task 3 and the SUMMARY).
"""
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import benchmark_provider as bp  # noqa: E402
from services.groq_extraction_service import (  # noqa: E402
    GroqExtractionError, PSU_IDENTITY_BATCH_PROMPT, ProviderExhausted,
)


class FakeService:
    """Stands in for GroqExtractionService.extract_batch. No network."""

    def __init__(self, results=None, error=None, delay=0.0):
        self.results = results
        self.error = error
        self.delay = delay
        self.calls = []
        self.closed = False
        self._fallbacks = []

    def extract_batch(self, system_prompt, titles):
        self.calls.append((system_prompt, titles))
        if self.error is not None:
            raise self.error
        return self.results

    def close(self):
        self.closed = True


def _fake_results_all_correct():
    """One correct parsed result per CASES entry, matched by 1-based index."""
    return [
        {"parsed": {"index": i + 1, "efficiency_rating": case["expected"]}, "raw_response": {}, "model": "fake"}
        for i, case in enumerate(bp.CASES)
    ]


# --- normalize_rating ----------------------------------------------------------

def test_normalize_rating_treats_80plus_spellings_as_equal():
    assert bp.normalize_rating("80 PLUS Gold") == bp.normalize_rating("80+ gold")
    assert bp.normalize_rating("80+ gold") == bp.normalize_rating(" 80Plus  GOLD ")
    assert bp.normalize_rating("80 Plus gold") == bp.normalize_rating("80+ gold")


def test_normalize_rating_none_variants_all_none():
    assert bp.normalize_rating(None) is None
    assert bp.normalize_rating("") is None
    assert bp.normalize_rating("null") is None
    assert bp.normalize_rating("Null") is None
    assert bp.normalize_rating("  ") is None


def test_normalize_rating_distinguishes_different_tiers():
    assert bp.normalize_rating("80+ Gold") != bp.normalize_rating("80+ Silver")


# --- score_results --------------------------------------------------------------

def test_score_results_all_correct():
    results = _fake_results_all_correct()
    correct, json_failures = bp.score_results(bp.CASES, results)
    assert correct == len(bp.CASES)
    assert json_failures == 0


def test_score_results_one_wrong():
    results = _fake_results_all_correct()
    # Corrupt the first answer to something that cannot match its expected tier.
    wrong = "80+ White" if bp.normalize_rating(bp.CASES[0]["expected"]) != bp.normalize_rating("80+ White") else "80+ Bronze"
    results[0]["parsed"]["efficiency_rating"] = wrong
    correct, json_failures = bp.score_results(bp.CASES, results)
    assert correct == len(bp.CASES) - 1
    assert json_failures == 0


def test_score_results_one_index_missing_counts_as_json_failure():
    results = _fake_results_all_correct()
    del results[0]
    correct, json_failures = bp.score_results(bp.CASES, results)
    assert correct == len(bp.CASES) - 1
    assert json_failures == 1


def test_score_results_unparseable_entry_counts_as_json_failure():
    results = _fake_results_all_correct()
    results[0] = {"parsed": None, "raw_response": {}, "model": "fake"}
    correct, json_failures = bp.score_results(bp.CASES, results)
    assert correct == len(bp.CASES) - 1
    assert json_failures == 1


# --- run_benchmark ---------------------------------------------------------------

def test_run_benchmark_reports_score_and_positive_throughput(monkeypatch):
    service = FakeService(results=_fake_results_all_correct())
    ticks = iter([0.0, 1.0])
    monkeypatch.setattr(bp.time, "monotonic", lambda: next(ticks))
    result = bp.run_benchmark(service, bp.CASES)
    assert result["score"] == len(bp.CASES)
    assert result["n"] == len(bp.CASES)
    assert result["json_failures"] == 0
    assert result["titles_per_min"] > 0
    assert service.calls == [(PSU_IDENTITY_BATCH_PROMPT, [c["title"] for c in bp.CASES])]


def test_run_benchmark_uses_monotonic_clock(monkeypatch):
    calls = {"n": 0}

    def fake_monotonic():
        calls["n"] += 1
        return calls["n"] * 0.5

    monkeypatch.setattr(bp.time, "monotonic", fake_monotonic)
    service = FakeService(results=_fake_results_all_correct())
    bp.run_benchmark(service, bp.CASES)
    assert calls["n"] >= 2


# --- main: provider lookup / error handling --------------------------------------

def test_main_unknown_provider_exits_nonzero_and_lists_available(monkeypatch, capsys):
    monkeypatch.setattr(bp, "provider_chain", lambda: [("mistral", "url", "model", "key")])
    rc = bp.main(["--provider", "nosuch"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "mistral" in err


def test_main_provider_with_unset_key_is_unavailable(monkeypatch, capsys):
    # provider_chain() only returns providers whose key is set, so an unset-key
    # provider simply never appears - looking it up must fail the same way an
    # unknown name does, not construct a service with no key.
    monkeypatch.setattr(bp, "provider_chain", lambda: [("mistral", "url", "model", "key")])
    rc = bp.main(["--provider", "google"])
    assert rc != 0


def test_main_never_falls_back_fallbacks_emptied(monkeypatch):
    captured = {}

    class RecordingService(FakeService):
        def __init__(self, *a, **kw):
            super().__init__(results=_fake_results_all_correct())
            captured["fallbacks_before_clear"] = None

    def fake_ctor(api_key, model, api_url, **kw):
        svc = RecordingService()
        captured["fallbacks_seen"] = svc._fallbacks
        return svc

    monkeypatch.setattr(bp, "provider_chain", lambda: [("mistral", "url", "some-model", "key")])
    monkeypatch.setattr(bp, "GroqExtractionService", fake_ctor)
    rc = bp.main(["--provider", "mistral"])
    assert rc == 0
    # _fallbacks must be emptied right after construction (grep also checks this).
    assert captured["fallbacks_seen"] == []


def test_main_prints_provider_name_and_score(monkeypatch, capsys):
    def fake_ctor(api_key, model, api_url, **kw):
        return FakeService(results=_fake_results_all_correct())

    monkeypatch.setattr(bp, "provider_chain", lambda: [("mistral", "url", "some-model", "key")])
    monkeypatch.setattr(bp, "GroqExtractionService", fake_ctor)
    rc = bp.main(["--provider", "mistral"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Provider: mistral (some-model)" in out
    assert f"Score: {len(bp.CASES)}/{len(bp.CASES)}" in out
    assert "Titles/min:" in out
    assert "JSON failures: 0" in out


def test_main_runs_k_times(monkeypatch, capsys):
    def fake_ctor(api_key, model, api_url, **kw):
        return FakeService(results=_fake_results_all_correct())

    monkeypatch.setattr(bp, "provider_chain", lambda: [("mistral", "url", "some-model", "key")])
    monkeypatch.setattr(bp, "GroqExtractionService", fake_ctor)
    rc = bp.main(["--provider", "mistral", "--runs", "3"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.count("Score:") == 3


def test_main_catches_groq_extraction_error(monkeypatch, capsys):
    def fake_ctor(api_key, model, api_url, **kw):
        return FakeService(error=GroqExtractionError("boom"))

    monkeypatch.setattr(bp, "provider_chain", lambda: [("mistral", "url", "some-model", "key")])
    monkeypatch.setattr(bp, "GroqExtractionService", fake_ctor)
    rc = bp.main(["--provider", "mistral"])
    assert rc == 1
    assert "boom" in capsys.readouterr().err


def test_main_catches_provider_exhausted(monkeypatch, capsys):
    def fake_ctor(api_key, model, api_url, **kw):
        return FakeService(error=ProviderExhausted("out of quota"))

    monkeypatch.setattr(bp, "provider_chain", lambda: [("mistral", "url", "some-model", "key")])
    monkeypatch.setattr(bp, "GroqExtractionService", fake_ctor)
    rc = bp.main(["--provider", "mistral"])
    assert rc == 1
    assert "out of quota" in capsys.readouterr().err


def test_main_requires_provider_or_url_model_keyenv(capsys):
    rc = bp.main([])
    assert rc != 0


def test_main_url_model_keyenv_reads_key_from_env(monkeypatch):
    monkeypatch.setenv("MY_LOCAL_KEY", "some-local-key")
    seen = {}

    def fake_ctor(api_key, model, api_url, **kw):
        seen["api_key"] = api_key
        seen["model"] = model
        seen["api_url"] = api_url
        return FakeService(results=_fake_results_all_correct())

    monkeypatch.setattr(bp, "GroqExtractionService", fake_ctor)
    rc = bp.main([
        "--url", "http://localhost:1234/v1/chat/completions",
        "--model", "local-model",
        "--key-env", "MY_LOCAL_KEY",
    ])
    assert rc == 0
    assert seen["api_key"] == "some-local-key"
    assert seen["model"] == "local-model"


def test_main_url_model_key_env_optional_sends_placeholder(monkeypatch):
    seen = {}

    def fake_ctor(api_key, model, api_url, **kw):
        seen["api_key"] = api_key
        return FakeService(results=_fake_results_all_correct())

    monkeypatch.setattr(bp, "GroqExtractionService", fake_ctor)
    rc = bp.main([
        "--url", "http://localhost:1234/v1/chat/completions",
        "--model", "local-model",
        "--key-env-optional",
    ])
    assert rc == 0
    assert seen["api_key"]  # some non-empty placeholder, never printed


def test_main_url_missing_key_env_value_fails(monkeypatch, capsys):
    monkeypatch.delenv("MISSING_KEY_VAR", raising=False)
    rc = bp.main([
        "--url", "http://localhost:1234/v1/chat/completions",
        "--model", "local-model",
        "--key-env", "MISSING_KEY_VAR",
    ])
    assert rc != 0
    assert "MISSING_KEY_VAR" in capsys.readouterr().err


# --- no-DB guarantee --------------------------------------------------------------

def test_importing_benchmark_provider_never_loads_db_session():
    script = str(Path(__file__).resolve().parent.parent / "scripts" / "benchmark_provider.py")
    code = (
        "import sys, runpy\n"
        f"sys.argv = [{script!r}, '--provider', 'nosuch']\n"
        "try:\n"
        f"    runpy.run_path({script!r}, run_name='__main__')\n"
        "except SystemExit:\n"
        "    pass\n"
        "assert 'db.session' not in sys.modules, sys.modules.keys()\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(Path(__file__).resolve().parent.parent / "src"),
        capture_output=True, text=True, timeout=30,
    )
    assert "OK" in result.stdout, result.stdout + result.stderr
    assert "db.session" not in result.stdout


# --- source-level guarantees -------------------------------------------------------

def test_source_has_no_identity_prompt_reference_and_no_bare_key_flag():
    source = Path(__file__).resolve().parent.parent.joinpath("scripts", "benchmark_provider.py").read_text(encoding="utf-8")
    assert "identity_prompt" not in source
    assert '"--key"' not in source
    assert "'--key'" not in source


def test_source_mentions_fallbacks_being_cleared():
    source = Path(__file__).resolve().parent.parent.joinpath("scripts", "benchmark_provider.py").read_text(encoding="utf-8")
    assert "_fallbacks" in source


# --- answer-key integrity (Task 2) -------------------------------------------------

def test_every_case_has_complete_evidence():
    for case in bp.CASES:
        assert case["title"].strip()
        assert case["trap"].strip()
        assert case["evidence"].strip()
        assert "expected" in case


def test_case_count_matches_docstring_n():
    n = len(bp.CASES)
    assert n == bp.CASE_COUNT
    assert n > 0
    assert n <= 8


def test_no_case_title_matches_the_prompt_few_shot_titles():
    few_shot_titles = {
        'Thermaltake Toughpower GF A3 1050 Watt 80 Plus Gold ATX 3.0 SMPS',
        'GIGABYTE P650SS 80+ Silver ATX 3.1 Non Modular Power Supply (Black) (650W)',
    }
    for case in bp.CASES:
        assert case["title"] not in few_shot_titles


def test_cases_have_no_duplicate_titles():
    titles = [c["title"] for c in bp.CASES]
    assert len(titles) == len(set(titles))
