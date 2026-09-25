"""The shared slowapi Limiter (SEC-03).

Lives in its own module, not main.py, so route modules (images.py, builder.py)
can import it directly without importing main.py first - main.py itself
imports those route modules to build its routers, so a route module importing
`api.main` would be a circular import.

Most settings below are read live off `configs.settings` at call time (via a
bound attribute lookup, never a value captured once at import time), so a
test can `monkeypatch.setattr(settings, "RATE_LIMIT_IMAGES", ...)` and have it
take effect on the very next request, with no module reload needed. slowapi
supports this directly: both `key_func` and any limit value passed as a
callable are re-evaluated on every request (see slowapi.wrappers.LimitGroup
and slowapi.extension.Limiter.__evaluate_limits, read from the installed
package this session). `default_limits` (below) uses this same callable
mechanism, so RATE_LIMIT_DEFAULT is also live.

The one exception is `enabled` (from RATE_LIMIT_ENABLED): slowapi's
`Limiter.__init__` takes this as a plain bool, not a callable, so it is read
from `settings.RATE_LIMIT_ENABLED` exactly once, at import time, when this
module's `limiter` is constructed - changing the env var afterward has no
effect on an already-running process (correct for the real deployment: it's
set once per process start). Tests that need to flip this at runtime
monkeypatch the `limiter.enabled` attribute directly (slowapi checks
`self.enabled` fresh on every request - read from the installed package this
session), not `settings.RATE_LIMIT_ENABLED`.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from configs import settings


def rate_limit_key(request: Request) -> str:
    """SEC-03: the rate-limit key is the socket address unless
    TRUST_CF_CONNECTING_IP is explicitly true. Otherwise anyone could set
    their own CF-Connecting-IP header to dodge the limit or frame another
    client - Cloudflare only guarantees the header once the origin is
    firewalled to Cloudflare's ranges only (Phase 3, OPS-02).
    """
    if settings.TRUST_CF_CONNECTING_IP:
        header = (request.headers.get("CF-Connecting-IP") or "").strip()
        if header:
            return header
    return get_remote_address(request)


limiter = Limiter(
    key_func=rate_limit_key,
    # A callable, not a plain string: re-read from settings on every request,
    # so RATE_LIMIT_DEFAULT stays test-controllable without a module reload
    # (see module docstring).
    default_limits=[lambda: settings.RATE_LIMIT_DEFAULT],
    # Unlike default_limits, `enabled` is a plain bool read once here, at
    # import time - see module docstring for why and how tests work around it.
    enabled=settings.RATE_LIMIT_ENABLED,
)
