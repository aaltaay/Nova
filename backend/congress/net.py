"""Every request the Congress reader sends, paced and bounded (ADR 066, decision 7).

One ``Net`` per reader: at least ``CONGRESS_REQUEST_GAP_SEC`` between any two requests, a timeout on each, and a body
limit (a response over it is refused, never half-read as if whole). Public GETs share a kept-alive session
(``http_pool``); the Senate needs its own cookies, so ``senate.py`` passes a session of its own. Tests pass a fake.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable

import requests

import http_pool
from congress.constants_congress import CONGRESS_HTTP_TIMEOUT_SEC, CONGRESS_REQUEST_GAP_SEC, CONGRESS_USER_AGENT


class TooLarge(Exception):
    """A response bigger than the reader accepts for it."""


class Net:
    def __init__(self, gap_sec: float = CONGRESS_REQUEST_GAP_SEC, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self._gap, self._sleep, self._clock = gap_sec, sleep, clock
        self._lock = threading.Lock()
        self._last = float("-inf")

    def _pace(self) -> None:
        with self._lock:
            wait = self._last + self._gap - self._clock()
            if wait > 0:
                self._sleep(wait)
            self._last = self._clock()

    def request(self, method: str, url: str, *, session: requests.Session | None = None, max_bytes: int | None = None,
                headers: dict | None = None, data: dict | None = None) -> requests.Response:
        self._pace()
        s = session or http_pool.session("congress")
        resp = s.request(method, url, data=data, timeout=CONGRESS_HTTP_TIMEOUT_SEC, stream=max_bytes is not None,
                         headers={"User-Agent": CONGRESS_USER_AGENT, **(headers or {})})
        if max_bytes is not None:
            body = bytearray()
            for chunk in resp.iter_content(64 * 1024):
                body.extend(chunk)
                if len(body) > max_bytes:
                    resp.close()
                    raise TooLarge(f"{url} is over {max_bytes // 1024} KB")
            resp._content = bytes(body)  # noqa: SLF001 -- requests' own field for a body already read
        return resp

    def get(self, url: str, **kw) -> requests.Response:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw) -> requests.Response:
        return self.request("POST", url, **kw)
