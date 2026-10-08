"""Per-install agent tokens (AGENT-04).

A token is shown once, when it is created, and only its SHA-256 is stored. Revoking
sets revoked_at, and authenticate() checks that on every request, so a revoke takes
effect on the agent's next call.
"""
import hashlib
import re
import secrets
from datetime import datetime, timezone

from sqlalchemy import select

from db.models.scrape_agent import ScrapeAgent

TOKEN_PREFIX = "pcba_"
_NAME = re.compile(r"[A-Za-z0-9._-]{1,50}")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_agent(session, name: str) -> tuple[ScrapeAgent, str]:
    """Create an agent and return it with its token. The token can't be shown again."""
    if not _NAME.fullmatch(name or ""):
        raise ValueError("agent name must be 1-50 letters, digits, '.', '_' or '-'")
    if session.execute(select(ScrapeAgent.id).where(ScrapeAgent.name == name)).first():
        raise ValueError(f"an agent named {name!r} already exists")
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    agent = ScrapeAgent(name=name, token_hash=hash_token(token))
    session.add(agent)
    session.commit()
    return agent, token


def authenticate(session, token: str | None) -> ScrapeAgent | None:
    """The agent this token belongs to, or None if it is missing, unknown or revoked."""
    if not token or not token.startswith(TOKEN_PREFIX):
        return None
    agent = session.execute(
        select(ScrapeAgent).where(ScrapeAgent.token_hash == hash_token(token))
    ).scalar_one_or_none()
    if agent is None or agent.revoked_at is not None:
        return None
    return agent


def revoke_agent(session, name: str, now: datetime | None = None) -> bool:
    """Revoke by name. False if there is no such agent. Revoking twice is harmless."""
    agent = session.execute(select(ScrapeAgent).where(ScrapeAgent.name == name)).scalar_one_or_none()
    if agent is None:
        return False
    if agent.revoked_at is None:
        agent.revoked_at = now or _utcnow()
        session.commit()
    return True


def list_agents(session) -> list[ScrapeAgent]:
    return list(session.execute(select(ScrapeAgent).order_by(ScrapeAgent.name)).scalars())
