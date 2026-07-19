"""Validate outbound alert webhook URLs (SEC-008 SSRF hardening)."""
from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse

from constants import (
    ALERTS_WEBHOOK_ALLOWED_SCHEMES,
    ALERTS_WEBHOOK_HOST_ALLOWLIST_DEFAULT,
)

# Hostnames that resolve to cloud metadata / well-known SSRF targets.
_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata",
        "metadata.aws.internal",
    }
)


def _host_allowlist() -> set[str]:
    raw = (os.environ.get("NOVA_WEBHOOK_HOST_ALLOWLIST") or "").strip()
    if raw:
        return {h.strip().lower().rstrip(".") for h in raw.split(",") if h.strip()}
    return {h.lower() for h in ALERTS_WEBHOOK_HOST_ALLOWLIST_DEFAULT}


def _is_blocked_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _hostname_resolves_blocked(hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"webhook_url host could not be resolved: {hostname}") from exc
    for info in infos:
        ip_str = info[4][0]
        try:
            if _is_blocked_ip(ipaddress.ip_address(ip_str)):
                return True
        except ValueError:
            continue
    return False


def validate_webhook_url(url: str | None) -> str:
    """Return a normalized URL or raise ValueError if unsafe / invalid."""
    if not url or not str(url).strip():
        raise ValueError("webhook_url is required")
    raw = str(url).strip()
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALERTS_WEBHOOK_ALLOWED_SCHEMES:
        raise ValueError(
            f"webhook_url scheme must be one of {ALERTS_WEBHOOK_ALLOWED_SCHEMES}"
        )
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not hostname:
        raise ValueError("webhook_url missing host")
    if hostname in _BLOCKED_HOSTNAMES or hostname.endswith(".localhost"):
        raise ValueError("webhook_url host is not allowed")
    # Literal IP in the URL
    try:
        if _is_blocked_ip(ipaddress.ip_address(hostname)):
            raise ValueError("webhook_url must not target a private or link-local address")
    except ValueError as exc:
        if "must not target" in str(exc):
            raise
        # hostname is not a literal IP — resolve below
    allowlist = _host_allowlist()
    if allowlist and hostname not in allowlist and not any(
        hostname.endswith(f".{suffix}") for suffix in allowlist
    ):
        raise ValueError(
            f"webhook_url host {hostname!r} is not in NOVA_WEBHOOK_HOST_ALLOWLIST"
        )
    if _hostname_resolves_blocked(hostname):
        raise ValueError("webhook_url resolves to a private or link-local address")
    return raw
