try:
    from curl_cffi import requests
    HAS_CURL_CFFI = True
except ImportError:
    import requests
    HAS_CURL_CFFI = False

from urllib.parse import urlsplit

from scrapers.store_hosts import is_store_host


class ServerFetchRefused(RuntimeError):
    """A store page was requested from the server in production (AGENT-08)."""


def _is_production() -> bool:
    # Read at call time, not import time, so the setting in force is the one used.
    from configs import settings

    return settings.ENV == "production"


class HttpClient:

    def __init__(
        self,
        impersonate: str = "chrome",
        timeout: int = 30,
    ):
        self.impersonate = impersonate
        self.timeout = timeout
        self.session = requests.Session()

    def get(self, url: str, **kwargs):
        # In production, store pages come only through agent jobs: the server's own IP
        # never scrapes a retailer. Development keeps working for tests and debugging.
        if _is_production() and is_store_host(urlsplit(url).hostname):
            raise ServerFetchRefused(
                f"refusing to fetch {urlsplit(url).hostname} from the server in production; "
                "store pages come through agent jobs"
            )
        req_kwargs = {
            "timeout": kwargs.get("timeout", self.timeout),
            "headers": kwargs.get("headers"),
            "cookies": kwargs.get("cookies"),
            "allow_redirects": kwargs.get("allow_redirects", True),
        }
        if HAS_CURL_CFFI:
            req_kwargs["impersonate"] = kwargs.get("impersonate", self.impersonate)

        response = self.session.get(url, **req_kwargs)
        response.raise_for_status()
        return response

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()