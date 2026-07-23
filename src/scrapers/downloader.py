"""
HTTP downloader used by all scrapers.
"""

from typing import Optional

import requests

from configs.settings import DEFAULT_HEADERS, REQUEST_TIMEOUT


class Downloader:
    """Wrapper around requests.Session."""

    def __init__(
        self,
        headers: Optional[dict] = None,
        timeout: int = REQUEST_TIMEOUT,
    ) -> None:
        self.session = requests.Session()
        self.session.headers.update(headers or DEFAULT_HEADERS)
        self.timeout = timeout

    def get(self, url: str, **kwargs) -> requests.Response:
        """
        Perform a GET request.

        Raises:
            requests.HTTPError
        """
        response = self.session.get(
            url,
            timeout=self.timeout,
            **kwargs,
        )

        response.raise_for_status()

        return response

    def close(self) -> None:
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()