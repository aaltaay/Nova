"""Install token for Open in Nova.

Owner: this module reads and writes ``open-in-nova-token.json`` under the cache dir.
Invalidation: an unknown ``schema_version`` refuses loud. Process start does not rotate the token.
schema_version: 1.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
from pathlib import Path

from paths import cache_dir

TOKEN_SCHEMA = 1
TOKEN_FILENAME = "open-in-nova-token.json"


class TokenError(RuntimeError):
    """The token file is there and this process will not guess past it."""


def token_path() -> Path:
    return cache_dir() / TOKEN_FILENAME


def load_or_create() -> dict:
    """The install token. Created once, mode 0o600, never rotated on startup."""
    path = token_path()
    if path.is_file():
        return _read(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"schema_version": TOKEN_SCHEMA, "token": secrets.token_hex(32)}
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        return _read(path)
    try:
        os.write(fd, json.dumps(body).encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(path, 0o600)
    return body


def token_matches(provided: str | None) -> bool:
    try:
        expected = str(load_or_create().get("token") or "")
    except TokenError:
        return False
    got = (provided or "").strip()
    if not expected or not got:
        return False
    return hmac.compare_digest(got, expected)


def _read(path: Path) -> dict:
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TokenError(f"open-in-nova token file cannot be read: {exc}") from exc
    if not isinstance(body, dict) or body.get("schema_version") != TOKEN_SCHEMA:
        version = body.get("schema_version") if isinstance(body, dict) else None
        raise TokenError(f"open-in-nova token schema {version!r} is not {TOKEN_SCHEMA}")
    token = body.get("token")
    if not isinstance(token, str) or not token:
        raise TokenError("open-in-nova token file has no token")
    return body
