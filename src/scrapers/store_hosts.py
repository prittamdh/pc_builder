"""The retailer domains agents fetch from (AGENT-08).

Kept as a fixed list, not read from the database, because the check it feeds has to hold
even when the database is unreachable or wrong. The same list goes into the extension's
manifest `host_permissions` (plan 02-05). A test fails if a store in the database is
missing here.
"""

STORE_DOMAINS = (
    "mdcomputers.in",
    "pcstudio.in",
    "vedantcomputers.com",
    "primeabgb.com",
    "elitehubs.com",
    "shop.clarioncomputers.in",
    "computechstore.in",
    "tpstech.in",
    "modxcomputers.com",
    "tlggaming.com",
)


def is_store_host(host: str | None) -> bool:
    """True for a store's domain or any subdomain of it (www., shop. ...)."""
    host = (host or "").lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in STORE_DOMAINS)
