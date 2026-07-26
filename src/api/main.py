from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes import builder, compare, products, stores

app = FastAPI(
    title="PC Builder API",
    description="REST API for PC component pricing, store comparisons, and historical price tracking.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(stores.router, prefix="/api/v1")
app.include_router(products.router, prefix="/api/v1")
app.include_router(builder.router, prefix="/api/v1")
app.include_router(compare.router, prefix="/api/v1")

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
