from curl_cffi import requests


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

        response = self.session.get(
            url,
            impersonate=kwargs.get("impersonate", self.impersonate),
            timeout=kwargs.get("timeout", self.timeout),
            headers=kwargs.get("headers"),
            cookies=kwargs.get("cookies"),
            allow_redirects=kwargs.get("allow_redirects", True),
        )

        response.raise_for_status()

        return response

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()