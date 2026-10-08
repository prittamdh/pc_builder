"""Agent tokens (plan 02-01, AGENT-04): shown once, stored hashed, revocable."""
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from db.models.scrape_agent import ScrapeAgent
from pipeline import agent_tokens

ROOT = Path(__file__).resolve().parent.parent


def test_the_token_is_stored_only_as_its_sha256(scratch_sessions):
    with scratch_sessions() as s:
        agent, token = agent_tokens.create_agent(s, "laptop")
        row = s.execute(select(ScrapeAgent)).scalar_one()
    assert token.startswith(agent_tokens.TOKEN_PREFIX)
    assert len(token) > 40
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in (row.name, row.token_hash)


def test_authenticate_accepts_the_token_and_refuses_everything_else(scratch_sessions):
    with scratch_sessions() as s:
        agent, token = agent_tokens.create_agent(s, "laptop")
        assert agent_tokens.authenticate(s, token).id == agent.id
        for bad in (None, "", " ", token + "x", token[:-1], agent_tokens.hash_token(token)):
            assert agent_tokens.authenticate(s, bad) is None, bad


def test_a_revoked_token_is_refused_on_its_next_use(scratch_sessions):
    with scratch_sessions() as s:
        _agent, token = agent_tokens.create_agent(s, "laptop")
        assert agent_tokens.authenticate(s, token) is not None
        assert agent_tokens.revoke_agent(s, "laptop") is True
        assert agent_tokens.authenticate(s, token) is None
        assert agent_tokens.revoke_agent(s, "no-such-agent") is False


def test_names_are_unique_and_plain(scratch_sessions):
    with scratch_sessions() as s:
        agent_tokens.create_agent(s, "laptop")
        with pytest.raises(ValueError, match="exists"):
            agent_tokens.create_agent(s, "laptop")
        for bad in ("", "has space", "x" * 51, "semi;colon"):
            with pytest.raises(ValueError):
                agent_tokens.create_agent(s, bad)


def test_each_token_is_different(scratch_sessions):
    with scratch_sessions() as s:
        _a, t1 = agent_tokens.create_agent(s, "one")
        _b, t2 = agent_tokens.create_agent(s, "two")
    assert t1 != t2


def test_cli_help_lists_the_three_commands():
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "agent_tokens.py"), "--help"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout
    for command in ("create", "list", "revoke"):
        assert command in out


def test_a_revoked_agents_prices_can_be_found_and_removed(scratch_sessions):
    """AGENT-09: every price row can carry the agent and job that fetched it."""
    from sqlalchemy import delete, func

    from db.models.price_history import PriceHistory
    from db.models.product import Product
    from db.models.store import Store
    from pipeline import job_queue

    with scratch_sessions() as s:
        store = Store(name="md", display_name="md", domain="mdcomputers.in", search_endpoint="/")
        s.add(store)
        s.flush()
        product = Product(sid=store.id, pid="1", name="CPU", product_url="https://mdcomputers.in/p")
        s.add(product)
        s.commit()
        bad, _ = agent_tokens.create_agent(s, "leaked")
        good, _ = agent_tokens.create_agent(s, "desktop")
        job_id = job_queue.enqueue(s, store_id=store.id, job_type="category_page", url="https://mdcomputers.in/c")
        s.add_all([
            PriceHistory(product_id=product.id, price=100, agent_id=bad.id, job_id=job_id),
            PriceHistory(product_id=product.id, price=101, agent_id=good.id, job_id=job_id),
            PriceHistory(product_id=product.id, price=102),  # pre-agent history: no agent
        ])
        s.commit()

        agent_tokens.revoke_agent(s, "leaked")
        s.execute(delete(PriceHistory).where(PriceHistory.agent_id == bad.id))
        s.commit()
        left = s.execute(select(PriceHistory.price).order_by(PriceHistory.price)).scalars().all()
        assert [int(p) for p in left] == [101, 102]
        assert s.execute(select(func.count()).select_from(ScrapeAgent)).scalar_one() == 2
