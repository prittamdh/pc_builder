import html
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.rate_limit import limiter
from common.logger import get_logger
from configs import settings

logger = get_logger(__name__)

# SEC-02: refuse to start before anything imports db.connection (which would
# otherwise fail first with an unhelpful TypeError on a None DATABASE_URL).
settings.require_database_url()

from api.routes import builder, compare, images, products, stores

_docs_enabled = settings.ENV != "production"

app = FastAPI(
    title="PC Builder API",
    description="REST API for PC component pricing, store comparisons, and historical price tracking.",
    version="1.0.0",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

# CORS Middleware: explicit allow-list only, no credentials (SEC-01).
# The app has no cookies or sessions, so credentials are never needed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# SEC-05: baseline security headers on every response. The CSP keeps
# 'unsafe-inline' for script-src/style-src this phase because index.html and
# app.js use inline onclick= and style= attributes that a strict policy would
# silently break; tightening (moving to addEventListener/external CSS) is a
# later item. No HSTS header here - that belongs to the Phase 3 proxy (setting
# it from this app would poison developer browsers on plain HTTP).
_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "object-src 'none'",
])


def apply_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = _CSP
    return response


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    return apply_security_headers(response)


# SEC-03: per-IP rate limiting. app.state.limiter is where slowapi's own
# middleware/decorators look up the limiter for a given app; SlowAPIMiddleware
# enforces default_limits on every route (even ones with no @limiter.limit of
# their own, e.g. /health), while /images and /builder/* add tighter,
# route-specific limits directly on their endpoints.
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


# The handler is a plain sync function, not `async def`, on purpose: slowapi's
# SlowAPIMiddleware enforces default_limits by calling the matched exception
# handler directly and synchronously (read from the installed package this
# session - it falls back to slowapi's own generic handler whenever the
# registered handler is a coroutine function), so an async handler here would
# silently never run for a default-limit rejection. Applying the security
# headers inside the handler itself (rather than relying on the middleware
# stack's ordering) guarantees a 429 always carries them.
def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return apply_security_headers(
        JSONResponse({"detail": "Too many requests. Please slow down."}, status_code=429)
    )


app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


# Register routers
app.include_router(stores.router, prefix="/api/v1")
app.include_router(products.router, prefix="/api/v1")
app.include_router(builder.router, prefix="/api/v1")
app.include_router(compare.router, prefix="/api/v1")
app.include_router(images.router, prefix="/api/v1")

# Mount Static UI Files
static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", include_in_schema=False)
def serve_index():
    return FileResponse(static_dir / "index.html")


# WEB-01: a bad URL for a page shows the branded 404 page; a bad /api/* path
# stays plain JSON (FastAPI's default behavior, kept via http_exception_handler).
@app.exception_handler(StarletteHTTPException)
async def branded_404(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404 and not request.url.path.startswith("/api/"):
        return apply_security_headers(FileResponse(static_dir / "404.html", status_code=404))
    return await http_exception_handler(request, exc)


# WEB-02: an unhandled exception never reaches the visitor as a traceback or
# framework-identifying text. Logged server-side only.
@app.exception_handler(Exception)
async def branded_500(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    if request.url.path.startswith("/api/"):
        return apply_security_headers(
            JSONResponse({"detail": "Internal server error."}, status_code=500)
        )
    return apply_security_headers(FileResponse(static_dir / "500.html", status_code=500))


@app.get("/privacy", include_in_schema=False)
def serve_privacy():
    return FileResponse(static_dir / "privacy.html")


@app.get("/about", include_in_schema=False)
def serve_about():
    # Read settings.CONTACT_EMAIL at request time (not import time) so the
    # owner's later .env change takes effect after a restart, and so tests
    # can monkeypatch it. Never hardcode a contact address (WEB-05, owner
    # decision #6 still open).
    contact_email = settings.CONTACT_EMAIL
    if contact_email:
        safe = html.escape(contact_email)
        contact_html = f'email us at <a href="mailto:{safe}">{safe}</a>.'
    else:
        contact_html = "a dedicated contact address for retailers is coming soon."
    body = (static_dir / "about.html").read_text(encoding="utf-8")
    body = body.replace("{{CONTACT}}", contact_html)
    return Response(content=body, media_type="text/html")


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "app": "PC Builder API"}


# SEO-01: robots.txt and a minimal sitemap. The canonical link on index.html
# is relative because no production domain exists yet; Phase 3 (plan 03-02)
# switches it and this sitemap's <loc> base to the real domain and turns on
# uvicorn's proxy headers so request.base_url reports https/the real host
# behind the proxy.
@app.get("/robots.txt", include_in_schema=False)
def robots_txt(request: Request):
    sitemap_url = str(request.base_url).rstrip("/") + "/sitemap.xml"
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        f"Sitemap: {sitemap_url}\n"
    )
    return PlainTextResponse(body)


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml(request: Request):
    base = str(request.base_url).rstrip("/")
    urls = "".join(f"<url><loc>{base}/{path}</loc></url>" for path in ("", "about", "privacy"))
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{urls}"
        "</urlset>"
    )
    return Response(content=xml, media_type="application/xml")
