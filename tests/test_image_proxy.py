"""The image route fetches server-side, so it must only ever fetch from store hosts."""
from api.routes.images import _host, is_allowed

HOSTS = frozenset({"pcstudio.in", "mdcomputers.in"})


def test_store_image_allowed():
    assert is_allowed("https://www.pcstudio.in/wp-content/uploads/x.webp", HOSTS)
    assert is_allowed("https://mdcomputers.in/image/catalog/a.jpg", HOSTS)


def test_subdomain_of_store_allowed():
    assert is_allowed("https://cdn.mdcomputers.in/a.jpg", HOSTS)


def test_other_hosts_refused():
    assert not is_allowed("https://evil.example/a.jpg", HOSTS)
    assert not is_allowed("http://127.0.0.1:8000/admin", HOSTS)
    assert not is_allowed("http://169.254.169.254/latest/meta-data", HOSTS)


def test_lookalike_host_refused():
    assert not is_allowed("https://notpcstudio.in/a.jpg", HOSTS)
    assert not is_allowed("https://pcstudio.in.evil.example/a.jpg", HOSTS)


def test_non_http_schemes_refused():
    assert not is_allowed("file:///etc/passwd", HOSTS)
    assert not is_allowed("ftp://pcstudio.in/a.jpg", HOSTS)


def test_host_normalises_www():
    assert _host("https://WWW.PCStudio.in/x") == "pcstudio.in"


def test_store_cdns_allowed_exactly():
    assert is_allowed("https://cdn.shopify.com/s/files/1/x.jpg", HOSTS)
    assert is_allowed("https://tlggaming.b-cdn.net/a.webp", HOSTS)
    assert not is_allowed("https://someoneelse.b-cdn.net/a.webp", HOSTS)
