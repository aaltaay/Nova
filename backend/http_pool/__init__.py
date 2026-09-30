"""Kept-alive HTTPS sessions for the background readers that poll the same host all day.

A bare ``requests.get`` builds a new session each call: a new TCP connection,
a new TLS handshake, and a new SSL context that reads the certificate bundle
again. The catalyst readers (Finnhub company news, Alpaca news) and the
scanner's news badge call one host every few seconds each, and on 2026-09-30
that setup took about a quarter of one CPU core of the backend (py-spy: the
time sat in urllib3's ``load_verify_locations``). One session per reader keeps
its connection open between calls, so only the first call -- and the first
after a drop -- pays for it.

A reader keeps its own session (``get("finnhub", ...)``), so a slow host never
holds another reader's connection. ``requests.Session`` is safe to share for
plain GETs with no cookies, which is all these readers send.
"""
from __future__ import annotations

import threading
from typing import Any

import requests

_lock = threading.Lock()
_sessions: dict[str, requests.Session] = {}


def session(name: str) -> requests.Session:
    """The reader's own kept-alive session, made on first use."""
    with _lock:
        s = _sessions.get(name)
        if s is None:
            s = requests.Session()
            _sessions[name] = s
        return s


def get(name: str, url: str, **kwargs: Any) -> requests.Response:
    """``requests.get`` on the reader's kept-alive session (same arguments, same response)."""
    return session(name).get(url, **kwargs)


def close_all() -> None:
    """Drop every session (tests, shutdown); the next call opens a new one."""
    with _lock:
        sessions = list(_sessions.values())
        _sessions.clear()
    for s in sessions:
        s.close()
