"""The Cryptos page's HTTP (ADR 040): one GET / POST for the public sources, one error type, one number reader.

A source that fails raises ``SourceError`` with a short reason the page can show as it is ("timed out after
10 s", "HTTP 429 (rate limited)"). Parsers raise it too when an answer is not the shape the source documents,
so a changed API reads as a stated failure, never as zeros.
"""
from __future__ import annotations

import math
from typing import Any

import requests

from constants_crypto import CRYPTO_HTTP_TIMEOUT_SEC, CRYPTO_USER_AGENT


class SourceError(RuntimeError):
    """A source did not answer, or answered something Nova cannot read. The message is shown on the page."""


def num(value: Any) -> float | None:
    """A finite number from a JSON value (numbers or numeric strings); anything else is ``None``."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        out = float(value)
    elif isinstance(value, str):
        try:
            out = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return out if math.isfinite(out) else None


def get_json(url: str, *, params: dict | None = None, headers: dict | None = None,
             timeout: float = CRYPTO_HTTP_TIMEOUT_SEC) -> Any:
    try:
        resp = requests.get(url, params=params, headers=_headers(headers), timeout=timeout)
    except requests.Timeout as exc:
        raise SourceError(f"timed out after {timeout:.0f} s") from exc
    except requests.RequestException as exc:
        raise SourceError(f"could not connect ({type(exc).__name__})") from exc
    return _body(resp)


def post_json(url: str, body: Any, *, timeout: float = CRYPTO_HTTP_TIMEOUT_SEC) -> Any:
    try:
        resp = requests.post(url, json=body, headers=_headers(None), timeout=timeout)
    except requests.Timeout as exc:
        raise SourceError(f"timed out after {timeout:.0f} s") from exc
    except requests.RequestException as exc:
        raise SourceError(f"could not connect ({type(exc).__name__})") from exc
    return _body(resp)


def _headers(extra: dict | None) -> dict:
    out = {"User-Agent": CRYPTO_USER_AGENT, "Accept": "application/json"}
    if extra:
        out.update(extra)
    return out


def _body(resp: Any) -> Any:
    status = int(getattr(resp, "status_code", 0) or 0)
    if status == 429:
        raise SourceError("HTTP 429 (rate limited)")
    if status in (401, 403, 451):
        raise SourceError(f"HTTP {status} (refused from this network)")
    if status != 200:
        raise SourceError(f"HTTP {status}")
    try:
        return resp.json()
    except ValueError as exc:
        raise SourceError("answered something that is not JSON") from exc
