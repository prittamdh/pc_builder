"""Endpoints the browser-extension agents call (plan 02-04). Contract: docs/AGENT_PROTOCOL.md.

Every call needs `Authorization: Bearer <token>` (401 otherwise, checked on every
request so a revoke takes effect at once), is rate-limited per token, and is left out of
the OpenAPI schema. Request bodies are read with a size cap before any JSON parsing, and
the database work runs in the threadpool so a big upload doesn't stall other requests.
"""
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from api.deps import get_db
from api.rate_limit import limiter, rate_limit_key
from configs import settings
from db.models.scrape_agent import ScrapeAgent
from pipeline import agent_tokens, job_queue, scrape_results
from pipeline.health import pipeline_report

router = APIRouter(prefix="/api/agent", include_in_schema=False)
health_router = APIRouter(include_in_schema=False)

# A result carries a page of at most 5 MB (checked, and stored as a rejection, by
# scrape_results); JSON escaping adds some. Anything past this isn't read at all.
MAX_RESULT_REQUEST_BYTES = 8 * 1024 * 1024
MAX_SMALL_REQUEST_BYTES = 64 * 1024


def agent_rate_key(request: Request) -> str:
    """One counter per token (hashed, so tokens never sit in limiter storage)."""
    header = request.headers.get("Authorization") or ""
    if header:
        return "agent:" + hashlib.sha256(header.encode("utf-8")).hexdigest()[:32]
    return rate_limit_key(request)


def current_agent(request: Request, db: Session = Depends(get_db)) -> ScrapeAgent:
    scheme, _, token = (request.headers.get("Authorization") or "").partition(" ")
    agent = agent_tokens.authenticate(db, token.strip()) if scheme.lower() == "bearer" else None
    if agent is None:
        raise HTTPException(401, "missing, unknown or revoked agent token", headers={"WWW-Authenticate": "Bearer"})
    return agent


async def _read_json(request: Request, model: type[BaseModel], limit: int) -> BaseModel:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(413, f"request over {limit} bytes")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, f"request over {limit} bytes")
        chunks.append(chunk)
    raw = b"".join(chunks) or b"{}"
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(400, json.loads(exc.json(include_url=False, include_input=False)))


class LeaseRequest(BaseModel):
    max_jobs: int = Field(10, ge=1, le=job_queue.MAX_LEASE_BATCH)


class ResultRequest(BaseModel):
    job_id: int
    lease_id: str = Field(max_length=64)
    final_url: str | None = Field(None, max_length=4096)
    http_status: int | None = Field(None, ge=100, le=599)
    content_type: str | None = Field(None, max_length=255)
    body: str | None = None
    error: str | None = Field(None, max_length=500)


class HeartbeatRequest(BaseModel):
    extension_version: str | None = Field(None, max_length=32)


@router.post("/lease")
@limiter.limit(lambda: settings.RATE_LIMIT_AGENT, key_func=agent_rate_key)
async def lease(request: Request, agent: ScrapeAgent = Depends(current_agent), db: Session = Depends(get_db)):
    body = await _read_json(request, LeaseRequest, MAX_SMALL_REQUEST_BYTES)
    jobs = await run_in_threadpool(job_queue.lease, db, agent.id, body.max_jobs)
    return {"jobs": [
        {
            "job_id": j.job_id,
            "lease_id": j.lease_id,
            "url": j.url,
            "headers": j.headers,
            "store_host": j.store_host,
            "not_before": j.not_before.isoformat(timespec="seconds"),
        }
        for j in jobs
    ]}


@router.post("/result")
@limiter.limit(lambda: settings.RATE_LIMIT_AGENT, key_func=agent_rate_key)
async def result(request: Request, agent: ScrapeAgent = Depends(current_agent), db: Session = Depends(get_db)):
    body = await _read_json(request, ResultRequest, MAX_RESULT_REQUEST_BYTES)
    upload = scrape_results.Upload(
        final_url=body.final_url, http_status=body.http_status, content_type=body.content_type,
        body=body.body, error=body.error,
    )
    try:
        outcome = await run_in_threadpool(
            job_queue.complete, db, body.job_id, body.lease_id, agent.id, upload, scrape_results.process_upload,
        )
    except job_queue.StaleLease:
        raise HTTPException(409, "lease is not current; drop this job")
    # The stored outcome also holds counts and the page's product ids (for pagination);
    # the agent only needs to know what happened.
    return {"job_id": body.job_id, "status": outcome["status"], "reason": outcome.get("reason")}


@router.post("/heartbeat")
@limiter.limit(lambda: settings.RATE_LIMIT_AGENT, key_func=agent_rate_key)
async def heartbeat(request: Request, agent: ScrapeAgent = Depends(current_agent), db: Session = Depends(get_db)):
    await _read_json(request, HeartbeatRequest, MAX_SMALL_REQUEST_BYTES)

    def touch():
        agent.last_seen_at = job_queue.utcnow()
        db.commit()

    await run_in_threadpool(touch)
    return {"ok": True}


@health_router.get("/health/pipeline")
def pipeline_health(db: Session = Depends(get_db)):
    """503 when prices have stopped flowing (AGENT-12). Watched by the uptime monitor."""
    report = pipeline_report(db)
    return JSONResponse(report, status_code=503 if report["problems"] else 200)
