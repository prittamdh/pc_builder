"""
Send one prompt through the free-provider chain (services.groq_extraction_service) and
print the answer. Optional helper for bulk data jobs, second opinions, and drafts, so
paid-model tokens aren't spent on things a free model can handle just as well.

SAFETY NET, NOT PERMISSION: this script refuses prompts that obviously contain a secret
or pasted source code, but that check is a last-resort net, not a license to try. Never
put source code or credentials into a prompt for this script in the first place - the
whole point of owning provider selection here is to keep third parties away from both.

Usage:
    python scripts/ask_free_ai.py "In one sentence, what is an 80 PLUS Gold PSU?"
    echo "prompt text" | python scripts/ask_free_ai.py
    python scripts/ask_free_ai.py --system "Reply as a single short sentence." "..."
    python scripts/ask_free_ai.py --json "..."

Read-only: makes one LLM call, prints the answer, exits. No --apply, nothing written.
"""
import argparse
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from services.groq_extraction_service import (  # noqa: E402
    GroqExtractionError, ProviderExhausted, default_service,
)

# Env vars whose *value* must never leave this machine, if it shows up verbatim in a
# prompt. Matched by name suffix, not an allowlist, so a new FOO_API_KEY is covered
# without editing this file.
_SECRET_ENV_SUFFIXES = ("_KEY", "_TOKEN", "_SECRET", "PASSWORD")
_MIN_SECRET_VALUE_LEN = 8

# Obvious key/token shapes, independent of whether they happen to be in this process's
# environment (e.g. a key copied from a teammate's .env).
_SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9]{10,}"),
    re.compile(r"\bgsk_[A-Za-z0-9]{10,}"),
    re.compile(r"\bAIza[A-Za-z0-9_\-]{10,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{10,}"),
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"postgres(?:ql)?://[^\s:/@]+:[^\s@/]+@"),
]

# A pasted source file, SQL, or diff: several lines that only look like this in real
# code/data, never in normal English. "let " is deliberately narrow (identifier then
# "=") so an ordinary sentence like "Let me know..." doesn't count.
_CODE_LINE_PATTERNS = [
    re.compile(r"^\s*(?:def |class |import |from \S+ import |<script)", re.IGNORECASE),
    re.compile(r"^\s*function\s+\w*\s*\("),
    re.compile(r"^\s*const\s+\w+\s*="),
    re.compile(r"^\s*let\s+\w+\s*="),
    re.compile(r"^\s*select\b.*\bfrom\b", re.IGNORECASE),
    re.compile(r"^\s*@@ "),
    re.compile(r"^\s*diff --git"),
    re.compile(r"^[A-Z][A-Z0-9_]*=\S"),  # env-file line, e.g. FOO_BAR=baz
]
_CODE_LINE_THRESHOLD = 3


def _is_code_line(line: str) -> bool:
    return any(pattern.search(line) for pattern in _CODE_LINE_PATTERNS)


def _env_secret_values() -> list[str]:
    """Values of environment variables that look like secrets, long enough to matter."""
    values = []
    for name, value in os.environ.items():
        if value and len(value) >= _MIN_SECRET_VALUE_LEN and name.upper().endswith(_SECRET_ENV_SUFFIXES):
            values.append(value)
    return values


def guard_reason(prompt: str) -> str | None:
    """
    Returns a reason the prompt must not be sent, or None if it looks safe.

    This is a safety net, not permission: callers must not rely on it to decide what's
    OK to paste here - the answer is "no source code, no secrets", full stop.
    """
    for value in _env_secret_values():
        if value in prompt:
            return "prompt contains the value of a *_KEY/*_TOKEN/*_SECRET/*PASSWORD environment variable"
    for pattern in _SECRET_PATTERNS:
        if pattern.search(prompt):
            return "prompt contains what looks like an API key, private key, or credentialed URL"
    code_lines = sum(1 for line in prompt.splitlines() if _is_code_line(line))
    if code_lines >= _CODE_LINE_THRESHOLD:
        return "prompt looks like pasted source code, SQL, or a diff (3+ matching lines)"
    return None


_FALLBACK_HTTP_STATUSES = re.compile(r"^Groq API error (401|402|403|404):")


def _is_auth_or_not_found_error(e: GroqExtractionError) -> bool:
    """True for the specific 401/402/403/404 statuses _call embeds in its message."""
    return bool(_FALLBACK_HTTP_STATUSES.match(str(e)))


def ask(prompt: str, system: str | None = None) -> tuple[dict, str]:
    """
    Sends prompt through the provider chain, following the same fallback pattern as
    GroqExtractionService.extract_batch (which _call itself does not do). Returns
    (parsed_json, model_name). Raises GroqExtractionError if every provider fails.
    """
    system_prompt = (
        'Reply to the user\'s message. Return STRICT JSON only, no other text: '
        '{"answer": "<your plain text reply>"}.'
    )
    if system:
        system_prompt += " Additional instructions: " + system

    service = default_service()
    try:
        while True:
            try:
                result = service._call(system_prompt, prompt)
                return result["parsed"], result["model"]
            except ProviderExhausted:
                if not service._fallbacks:
                    raise
                service._switch_to(*service._fallbacks.pop(0))
            except GroqExtractionError as e:
                # _call only raises the generic GroqExtractionError for a non-2xx,
                # non-429, non-5xx response (see its `resp.status_code != 200` branch),
                # with the status code embedded in the message. 401/402/403/404 mean
                # this provider's key/quota is bad, not that the prompt is bad - treat
                # it like ProviderExhausted rather than surfacing it as a hard failure.
                # Scoped to this script only; the service itself is not modified.
                if _is_auth_or_not_found_error(e) and service._fallbacks:
                    service._switch_to(*service._fallbacks.pop(0))
                else:
                    raise
    finally:
        service.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("prompt", nargs="?", default="-",
                     help='prompt text, or "-" (default) to read it from stdin')
    ap.add_argument("--system", default=None, help="extra system instructions")
    ap.add_argument("--json", action="store_true",
                     help='print {"answer":..., "model":...} instead of plain text')
    args = ap.parse_args(argv)

    if args.prompt == "-":
        if hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
            ap.print_usage(sys.stderr)
            print("ask_free_ai: no prompt given and stdin is a terminal", file=sys.stderr)
            return 2
        prompt = sys.stdin.read()
    else:
        prompt = args.prompt
    prompt = prompt.strip()
    if not prompt:
        print("ask_free_ai: empty prompt", file=sys.stderr)
        return 2

    reason = guard_reason(prompt)
    if reason:
        print(f"ask_free_ai: refusing to send prompt - {reason}", file=sys.stderr)
        return 2

    try:
        parsed, model = ask(prompt, system=args.system)
    except GroqExtractionError as e:
        print(f"ask_free_ai: all providers failed - {e}", file=sys.stderr)
        return 1

    answer = parsed.get("answer") if isinstance(parsed, dict) and "answer" in parsed else parsed

    if args.json:
        print(json.dumps({"answer": answer, "model": model}))
    else:
        print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
