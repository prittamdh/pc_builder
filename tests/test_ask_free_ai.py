"""
Tests for scripts/ask_free_ai.py. No network calls: the provider service is faked
(monkeypatched) so these only exercise the answer-extraction, fallback, guard, and
stdin-reading logic in the script itself.
"""
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ask_free_ai  # noqa: E402
from services.groq_extraction_service import GroqExtractionError, ProviderExhausted  # noqa: E402


class FakeService:
    """Stands in for GroqExtractionService: a scripted sequence of _call outcomes."""

    def __init__(self, plan, fallbacks=None):
        self.plan = list(plan)
        self.fallbacks_available = fallbacks if fallbacks is not None else []
        self._fallbacks = list(self.fallbacks_available)
        self.model = "initial-model"
        self.calls = []
        self.closed = False

    def _call(self, system_prompt, user_content, max_retries=4):
        self.calls.append((system_prompt, user_content))
        step = self.plan.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    def _switch_to(self, name, api_url, model, api_key):
        self.model = model

    def close(self):
        self.closed = True


def _patch_service(monkeypatch, service):
    monkeypatch.setattr(ask_free_ai, "default_service", lambda: service)


# --- answer extraction -----------------------------------------------------------

def test_ask_extracts_answer_field(monkeypatch):
    service = FakeService(plan=[
        {"parsed": {"answer": "An 80 PLUS Gold PSU is efficient."}, "raw_response": {}, "model": "m1"},
    ])
    _patch_service(monkeypatch, service)
    parsed, model = ask_free_ai.ask("what is a gold psu")
    assert parsed["answer"] == "An 80 PLUS Gold PSU is efficient."
    assert model == "m1"
    assert service.closed


def test_main_prints_answer_falls_back_to_parsed_json_if_key_missing(monkeypatch, capsys):
    service = FakeService(plan=[
        {"parsed": {"unexpected": "oops"}, "raw_response": {}, "model": "m1"},
    ])
    _patch_service(monkeypatch, service)
    rc = ask_free_ai.main(["hello there"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out == "{'unexpected': 'oops'}"


# --- provider fallback -------------------------------------------------------------

def test_ask_falls_back_to_next_provider_after_exhaustion(monkeypatch):
    service = FakeService(
        plan=[ProviderExhausted("out of quota"),
              {"parsed": {"answer": "second try worked"}, "raw_response": {}, "model": "m2"}],
        fallbacks=[("fallback", "url", "model2", "key2")],
    )
    _patch_service(monkeypatch, service)
    parsed, model = ask_free_ai.ask("prompt")
    assert parsed["answer"] == "second try worked"
    assert model == "m2"
    assert len(service.calls) == 2


@pytest.mark.parametrize("status", [401, 402, 403, 404])
def test_ask_falls_back_on_http_401_402_403_404(monkeypatch, status):
    service = FakeService(
        plan=[GroqExtractionError(f"Groq API error {status}: forbidden"),
              {"parsed": {"answer": "worked on fallback"}, "raw_response": {}, "model": "m2"}],
        fallbacks=[("fallback", "url", "model2", "key2")],
    )
    _patch_service(monkeypatch, service)
    parsed, model = ask_free_ai.ask("prompt")
    assert parsed["answer"] == "worked on fallback"
    assert model == "m2"


def test_ask_does_not_fall_back_on_other_groq_errors(monkeypatch):
    service = FakeService(
        plan=[GroqExtractionError("Groq returned non-JSON content: garbage")],
        fallbacks=[("fallback", "url", "model2", "key2")],
    )
    _patch_service(monkeypatch, service)
    with pytest.raises(GroqExtractionError):
        ask_free_ai.ask("prompt")


def test_main_errors_when_every_provider_exhausted(monkeypatch, capsys):
    service = FakeService(plan=[ProviderExhausted("out of quota")], fallbacks=[])
    _patch_service(monkeypatch, service)
    rc = ask_free_ai.main(["prompt"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "all providers failed" in err


def test_main_errors_when_no_keys_configured(monkeypatch, capsys):
    def raise_no_keys():
        raise GroqExtractionError("No provider API keys are configured.")
    monkeypatch.setattr(ask_free_ai, "default_service", raise_no_keys)
    rc = ask_free_ai.main(["prompt"])
    assert rc == 1
    assert "all providers failed" in capsys.readouterr().err


# --- secret/code guard --------------------------------------------------------------

def test_guard_refuses_env_secret_value(monkeypatch):
    monkeypatch.setenv("SOME_SERVICE_API_KEY", "abcdef1234567890")
    reason = ask_free_ai.guard_reason("please use abcdef1234567890 to authenticate")
    assert reason is not None


def test_guard_allows_short_env_secret_value(monkeypatch):
    # Below the minimum length - too generic to safely block on (e.g. "PASSWORD=1234567").
    monkeypatch.setenv("SOME_PASSWORD", "short1")
    assert ask_free_ai.guard_reason("the value is short1") is None


@pytest.mark.parametrize("secret", [
    "sk-abcdefghij1234567890",
    "gsk_abcdefghij1234567890",
    "AIzaSyAbcdefghij1234567890",
    "ghp_abcdefghij1234567890",
    "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA\n-----END RSA PRIVATE KEY-----",
    "postgres://myuser:mypassword@dbhost:5432/mydb",
])
def test_guard_refuses_known_key_shapes(secret):
    reason = ask_free_ai.guard_reason(f"here is some context around it: {secret} end")
    assert reason is not None


def test_guard_refuses_pasted_python_code():
    code = "\n".join([
        "import os",
        "def foo():",
        "class Bar:",
        "    pass",
    ])
    assert ask_free_ai.guard_reason(code) is not None


def test_guard_refuses_pasted_html_script():
    html = "\n".join([
        "<script>alert(1)</script>",
        "<script>more</script>",
        "<script>even more</script>",
    ])
    assert ask_free_ai.guard_reason(html) is not None


def test_guard_allows_normal_prompt_mentioning_class_once():
    prompt = "Explain the difference between a struct and a class in one sentence."
    assert ask_free_ai.guard_reason(prompt) is None


def test_guard_refuses_pasted_javascript():
    code = "\n".join([
        "function total(items) {",
        "  const sum = 0;",
        "  let count = 0;",
        "}",
    ])
    assert ask_free_ai.guard_reason(code) is not None


def test_guard_refuses_pasted_sql():
    sql = "\n".join([
        "SELECT * FROM users WHERE id = 1;",
        "SELECT name FROM products;",
        "SELECT price FROM listings;",
    ])
    assert ask_free_ai.guard_reason(sql) is not None


def test_guard_refuses_pasted_diff():
    diff = "\n".join([
        "diff --git a/foo.py b/foo.py",
        "@@ -1,3 +1,4 @@",
        "@@ -10,2 +10,3 @@",
    ])
    assert ask_free_ai.guard_reason(diff) is not None


def test_guard_refuses_pasted_env_file():
    env = "\n".join([
        "DATABASE_URL=postgres://x",
        "GROQ_API_KEY_UNUSED=abc",
        "SOME_FLAG=true",
    ])
    assert ask_free_ai.guard_reason(env) is not None


def test_guard_allows_let_me_know_sentence():
    prompt = "Let me know if this makes sense, and let the team decide on the rest."
    assert ask_free_ai.guard_reason(prompt) is None


def test_main_exits_2_and_sends_nothing_when_guarded(monkeypatch, capsys):
    called = {"hit": False}

    def fake_default_service():
        called["hit"] = True
        raise AssertionError("should never be called")

    monkeypatch.setattr(ask_free_ai, "default_service", fake_default_service)
    rc = ask_free_ai.main(["here is my sk-abcdefghij1234567890 key"])
    assert rc == 2
    assert not called["hit"]
    assert "refusing to send" in capsys.readouterr().err


# --- stdin ---------------------------------------------------------------------

def test_main_reads_prompt_from_stdin_when_no_arg(monkeypatch, capsys):
    service = FakeService(plan=[
        {"parsed": {"answer": "from stdin"}, "raw_response": {}, "model": "m1"},
    ])
    _patch_service(monkeypatch, service)
    monkeypatch.setattr(sys, "stdin", io.StringIO("what comes from stdin?\n"))
    rc = ask_free_ai.main([])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "from stdin"


def test_main_exits_2_on_terminal_stdin_with_no_prompt(monkeypatch, capsys):
    class TtyStdin:
        def isatty(self):
            return True

        def read(self):
            raise AssertionError("must not block reading from a terminal")

    monkeypatch.setattr(sys, "stdin", TtyStdin())
    rc = ask_free_ai.main([])
    assert rc == 2
    assert "usage" in capsys.readouterr().err.lower()


def test_main_reads_prompt_from_stdin_when_dash(monkeypatch, capsys):
    service = FakeService(plan=[
        {"parsed": {"answer": "dash stdin"}, "raw_response": {}, "model": "m1"},
    ])
    _patch_service(monkeypatch, service)
    monkeypatch.setattr(sys, "stdin", io.StringIO("prompt via dash\n"))
    rc = ask_free_ai.main(["-"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "dash stdin"


# --- --json flag -----------------------------------------------------------------

def test_main_json_flag_prints_answer_and_model(monkeypatch, capsys):
    service = FakeService(plan=[
        {"parsed": {"answer": "json answer"}, "raw_response": {}, "model": "m3"},
    ])
    _patch_service(monkeypatch, service)
    rc = ask_free_ai.main(["--json", "prompt"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out == '{"answer": "json answer", "model": "m3"}'
