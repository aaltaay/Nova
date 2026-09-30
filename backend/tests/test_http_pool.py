"""Kept-alive sessions for the background news readers (http_pool)."""
from __future__ import annotations

import logging.handlers

import requests

import http_pool


def test_a_reader_keeps_one_session_and_readers_do_not_share():
    http_pool.close_all()
    try:
        first = http_pool.session("finnhub_news")
        assert http_pool.session("finnhub_news") is first
        assert http_pool.session("alpaca_news") is not first
    finally:
        http_pool.close_all()


def test_get_goes_through_the_readers_session(monkeypatch):
    calls = []

    def fake_get(self, url, **kwargs):
        calls.append((self, url, kwargs))
        return "resp"

    monkeypatch.setattr(requests.Session, "get", fake_get)
    http_pool.close_all()
    try:
        assert http_pool.get("alpaca_news", "https://example.test/news", timeout=3) == "resp"
        assert http_pool.get("alpaca_news", "https://example.test/news", timeout=3) == "resp"
        assert calls[0][0] is calls[1][0] is http_pool.session("alpaca_news")
        assert calls[0][2] == {"timeout": 3}
    finally:
        http_pool.close_all()


def test_the_readers_call_the_pool_not_a_bare_get():
    """A bare ``requests.get`` is a new TLS setup per call (a quarter of a core on 2026-09-30)."""
    import inspect

    import scanner
    from catalysts import live, live_finnhub

    for fn in (live._fetch, live_finnhub._read, scanner._check_news):
        text = inspect.getsource(fn)
        assert "requests.get(" not in text, fn.__qualname__
        assert "http_pool.get(" in text, fn.__qualname__


def test_the_hod_trade_log_only_queues_on_the_callers_thread():
    """The IB loop logs every trade tick: the file write belongs to the listener thread."""
    from hod_momo_trade_log import trade_log

    # pytest 9.1 puts its own capture handlers on every logger (#651): judge only the backend's.
    ours = [h for h in trade_log.handlers if not type(h).__module__.startswith("_pytest")]
    assert ours
    assert all(isinstance(h, logging.handlers.QueueHandler) for h in ours)
    assert trade_log.propagate is False

