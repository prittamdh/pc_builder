from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from configs import settings

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


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "app": "PC Builder API"}
