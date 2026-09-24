"""
Product images, fetched server-side from the store that listed them.

The catalog used to hot-link store images straight into the page, and browsers refuse
some of them: PCStudio sends Cross-Origin-Resource-Policy: same-origin, so its images
never render on another site, and dead links on mdcomputers are blocked as ORB. The
server is not bound by either, so it fetches the image and serves it from our origin.

Only hosts belonging to a store in the database are fetched - anything else is refused,
so this cannot be used to make the server request arbitrary URLs. An image that cannot
be fetched is answered with a "No image" placeholder rather than an error status, since
a store's dead link is a fact about the data, not a fault in the page.
"""
import time
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_db
from db.models.store import Store

router = APIRouter(prefix="/images", tags=["Images"])

# Stores that host images off their own domain. Exact hostnames only: b-cdn.net serves
# any Bunny customer's files, so allowing the parent would allow anyone's.
IMAGE_CDN_HOSTS = frozenset({"cdn.shopify.com", "tlggaming.b-cdn.net"})

MAX_BYTES = 5 * 1024 * 1024
HOSTS_TTL_S = 600
_hosts_cache: tuple[float, frozenset[str]] = (0.0, frozenset())

PLACEHOLDER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 120">'
    '<rect x="1" y="1" width="158" height="118" rx="6" fill="none" stroke="#8886" stroke-dasharray="4 3"/>'
    '<text x="80" y="64" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#999">No image</text>'
    "</svg>"
).encode()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
}


def _host(url: str | None) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def store_hosts(db: Session) -> frozenset[str]:
    global _hosts_cache
    fetched_at, hosts = _hosts_cache
    if time.monotonic() - fetched_at < HOSTS_TTL_S and hosts:
        return hosts
    found = set()
    for domain, base_url in db.execute(select(Store.domain, Store.base_url)):
        for value in (domain, base_url):
            h = _host(value if value and "://" in value else f"https://{value or ''}")
            if h:
                found.add(h)
    hosts = frozenset(found)
    _hosts_cache = (time.monotonic(), hosts)
    return hosts


def is_allowed(url: str, hosts: frozenset[str]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    h = _host(url)
    if h in IMAGE_CDN_HOSTS:
        return True
    return any(h == allowed or h.endswith("." + allowed) for allowed in hosts)


def _placeholder() -> Response:
    return Response(PLACEHOLDER_SVG, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=3600"})


@router.get("")
def product_image(u: str = Query(..., max_length=2000), db: Session = Depends(get_db)):
    hosts = store_hosts(db)
    if not is_allowed(u, hosts):
        raise HTTPException(status_code=400, detail="Not a store image URL")
    try:
        with httpx.Client(timeout=8.0, follow_redirects=False, headers=HEADERS) as client:
            r = client.get(u)
            # Redirects are followed by hand so every hop is checked BEFORE it is
            # requested - a store link must not bounce the server anywhere else.
            for _ in range(3):
                if not r.is_redirect:
                    break
                nxt = str(r.next_request.url) if r.next_request else ""
                if not is_allowed(nxt, hosts):
                    return _placeholder()
                r = client.get(nxt)
    except httpx.HTTPError:
        return _placeholder()
    ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
    if r.status_code != 200 or not ctype.startswith("image/") or len(r.content) > MAX_BYTES:
        return _placeholder()
    return Response(r.content, media_type=ctype, headers={"Cache-Control": "public, max-age=86400"})
