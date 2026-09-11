"""Shared Finnhub 429 / Retry-After cooldown (D-015)."""
from __future__ import annotations

import time

import finnhub_http as fh


class _Resp:
    def __init__(self, retry_after=None):
        self.headers = {} if retry_after is None else {"Retry-After": retry_after}


def setup_function():
    fh.reset_for_testing()


def teardown_function():
    fh.reset_for_testing()


def test_parse_retry_after_uses_header_seconds():
    assert fh.parse_retry_after(_Resp("12")) == 12.0


def test_parse_retry_after_falls_back_on_junk():
    assert fh.parse_retry_after(_Resp("nope"), default=30.0) == 30.0


def test_note_rate_limit_blocks_until_retry_after(monkeypatch):
    now = 1_000_000.0
    monkeypatch.setattr(fh.time, "time", lambda: now)
    wait = fh.note_rate_limit(_Resp("8"))
    assert wait == 8.0
    assert fh.is_blocked(now)
    assert fh.remaining_sec(now) == 8.0
    assert not fh.is_blocked(now + 8.0)
