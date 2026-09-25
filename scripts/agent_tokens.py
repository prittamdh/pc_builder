"""
Create, list and revoke scrape-agent tokens (AGENT-04).

Each browser extension install gets its own token. The token is printed once, when it
is created; only its SHA-256 is stored, so it can't be shown again - create a new one
if it is lost. A revoke takes effect on the agent's next request. Revoked agents stay
listed, because the prices they saved still point at them.

Usage:
    python scripts/agent_tokens.py create --name laptop
    python scripts/agent_tokens.py list
    python scripts/agent_tokens.py revoke --name laptop
"""
import argparse
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Manage scrape-agent tokens.")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="create an agent and print its token once")
    create.add_argument("--name", required=True, help="e.g. laptop, desktop (letters, digits, . _ -)")
    sub.add_parser("list", help="list agents with last check-in and revoke time")
    revoke = sub.add_parser("revoke", help="revoke an agent's token")
    revoke.add_argument("--name", required=True)
    args = parser.parse_args(argv)

    # Imported after parsing so --help works without DATABASE_URL.
    from db.session import SessionLocal
    from pipeline import agent_tokens

    with SessionLocal() as session:
        if args.command == "create":
            try:
                agent, token = agent_tokens.create_agent(session, args.name)
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            print(f"Created agent {agent.name!r} (id {agent.id}).")
            print("Token - paste it into the extension's options page now; it is not shown again:")
            print(token)
        elif args.command == "list":
            agents = agent_tokens.list_agents(session)
            if not agents:
                print("No agents.")
            for a in agents:
                state = f"revoked {a.revoked_at:%Y-%m-%d %H:%M}" if a.revoked_at else "active"
                seen = f"{a.last_seen_at:%Y-%m-%d %H:%M} UTC" if a.last_seen_at else "never"
                print(f"{a.id:>4}  {a.name:<20} {state:<24} last seen {seen}")
        else:
            if not agent_tokens.revoke_agent(session, args.name):
                print(f"error: no agent named {args.name!r}", file=sys.stderr)
                return 1
            print(f"Revoked {args.name!r}. Its next request gets 401.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
