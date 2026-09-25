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
import slowapi.middleware as _slowapi_middleware
from starlette.requests import Request
from starlette.routing import Match

try:
    from fastapi.routing import _IncludedRouter
except ImportError:  # pragma: no cover - only missing on very old fastapi
    _IncludedRouter = None

from configs import settings


def _find_route_handler_including_lazy_routers(routes, scope):
    """Replacement for slowapi 0.1.10's `slowapi.middleware._find_route_handler`.

    That function walks `app.routes` looking for entries with a plain
    `.endpoint` attribute. Newer FastAPI (>=0.140) no longer flattens routes
    added via `include_router` into the parent app's route list at include
    time - each `include_router` call instead adds one `_IncludedRouter`
    placeholder, whose real routes only get resolved (with the prefix
    combined in) via its `_match()` method. Slowapi's original function
    doesn't know about `_IncludedRouter`, so it never finds a handler for any
    route added through `include_router` - which in this app is *every*
    `/api/v1/*` route not decorated with `@limiter.limit` directly - and
    `_should_exempt` then treats "no handler found" as "exempt", silently
    skipping `default_limits` for those routes entirely.

    This walks the same top-level route list, but for an `_IncludedRouter`
    resolves the actual matched route (recursing through nested routers, and
    correctly combining path prefixes) via its own `_match`, so
    `default_limits` reach every route, not just the ones defined directly on
    `app`.
    """
    handler = None
    for route in routes:
        if _IncludedRouter is not None and isinstance(route, _IncludedRouter):
            match, _child_scope, matched_route, _ctx = route._match(scope)
            if match == Match.FULL and matched_route is not None and hasattr(matched_route, "endpoint"):
                handler = matched_route.endpoint
            continue
        match, _ = route.matches(scope)
        if match == Match.FULL and hasattr(route, "endpoint"):
            handler = route.endpoint
    return handler


# slowapi's SlowAPIMiddleware calls `_find_route_handler` by module-global
# lookup on every request (see slowapi/middleware.py), so replacing the name
# in its module here takes effect for every request without touching main.py
# or the route modules.
_slowapi_middleware._find_route_handler = _find_route_handler_including_lazy_routers


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
    # slowapi's default key_style is "url" - it counts each *exact* URL
    # separately, so a parameterised route (/products/1, /products/2, ...) or
    # (/builder/builds/token-a, .../token-b, ...) gets one counter per value
    # and is effectively unlimited. "endpoint" keys by the matched route
    # pattern instead (e.g. "/api/v1/products/{product_id}"), so every value
    # of the path parameter shares one counter, as intended.
    key_style="endpoint",
)
