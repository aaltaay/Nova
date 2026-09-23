"""One paced HTTP GET for the fetchers: JSON or text, bounded retries on 429 / 5xx."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


class Pacer:
    """At most ``per_sec`` calls a second, across one fetcher."""

    def __init__(self, per_sec: float):
        self.gap = 1.0 / per_sec
        self.next = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        if now < self.next:
            time.sleep(self.next - now)
        self.next = max(now, self.next) + self.gap


class HttpRefused(Exception):
    """A 401 / 403 / 404: the source will not answer this request (no retry)."""

    def __init__(self, code: int, url: str):
        super().__init__(f"HTTP {code} for {url.split('?')[0]}")
        self.code = code


def get(url: str, headers: dict | None, pacer: Pacer, *, as_json: bool = True, tries: int = 5):
    delay = 2.0
    for attempt in range(tries):
        pacer.wait()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=30) as r:
                body = r.read()
            return json.loads(body) if as_json else body.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):
                raise HttpRefused(e.code, url) from None
            if attempt == tries - 1:
                raise
            time.sleep(delay * (4 if e.code == 429 else 1))
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == tries - 1:
                raise
            time.sleep(delay)
        delay *= 2
    raise RuntimeError("unreachable")
