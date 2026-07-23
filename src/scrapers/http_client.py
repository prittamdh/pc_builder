from curl_cffi import requests


class HttpClient:
    def __init__(self):
        self.session = requests.Session()

    def get(self, url: str):
        response = self.session.get(
            url,
            impersonate="chrome",
            timeout=30,
        )

        response.raise_for_status()

        return response

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()