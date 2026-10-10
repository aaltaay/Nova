"""The guard's rules as pure functions: no I/O, no logging, and the environment only as passed in.

``load_policy`` turns an environment mapping into a ``GuardPolicy`` once, when
the app is built; ``check_request`` judges one request's Host and Origin
headers against it. Every comparison is exact equality on a normalized name,
never a substring or suffix match.
"""
from __future__ import annotations

import ipaddress
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache

from api_process_guard import DEFAULT_API_HOST
from constants import CORS_ALLOWED_ORIGINS_DEFAULT, NOVA_API_LOOPBACK_HOSTS
from request_guard.constants_request_guard import (
    ALLOWED_HOSTS_ANY,
    ALLOWED_HOSTS_ENV,
    API_HOST_ENV,
    CORS_ANY_ORIGIN,
    CORS_ORIGINS_ENV,
    DESKTOP_WS_ORIGINS,
    HOST_HEADER_MAX_CHARS,
    HOST_NAME_CACHE_SIZE,
    NEVER_ALLOWED_ORIGINS,
    REASON_HOST_NOT_ALLOWED,
    REASON_ORIGIN_NOT_ALLOWED,
    WILDCARD_BIND_HOSTS,
)


@dataclass(frozen=True)
class GuardPolicy:
    hosts: frozenset[str]
    any_host: bool
    ws_origins: frozenset[str]


@dataclass(frozen=True)
class Refusal:
    header: str  # "Host" or "Origin"
    value: str  # what the request sent ("" when the header was missing)
    reason: str  # REASON_HOST_NOT_ALLOWED or REASON_ORIGIN_NOT_ALLOWED


def _is_port(text: str) -> bool:
    return text.isascii() and text.isdigit() and len(text) <= 5


def _canonical(name: str) -> str:
    """An IP literal in its one written form (``::0:1`` and ``::1`` are the same host)."""
    try:
        return ipaddress.ip_address(name).compressed
    except ValueError:
        return name


def host_name(raw: str | None) -> str | None:
    """The name in a Host header (``"[::1]:8000"`` -> ``"::1"``), or None when it is not one."""
    if raw is None or len(raw) > HOST_HEADER_MAX_CHARS:
        return None
    return _host_name(raw)


@lru_cache(maxsize=HOST_NAME_CACHE_SIZE)
def _host_name(raw: str) -> str | None:
    """Cached: every request carries a Host, the desk's is the same each time, and
    parsing an IP literal costs microseconds on the order path."""
    value = raw.strip().lower()
    if not value:
        return None
    if any(ch.isspace() for ch in value) or "@" in value or "/" in value:
        return None
    if value.startswith("["):
        # Brackets hold an IPv6 address and nothing else; a port may follow them.
        end = value.find("]")
        if end < 0:
            return None
        rest = value[end + 1:]
        if rest and not (rest.startswith(":") and _is_port(rest[1:])):
            return None
        try:
            return ipaddress.IPv6Address(value[1:end]).compressed
        except ValueError:
            return None
    if ":" in value:
        name, _, port = value.rpartition(":")
        # A bare IPv6 address (no brackets) is not a Host header a client sends.
        if not _is_port(port) or ":" in name:
            return None
    else:
        name = value
    name = name.rstrip(".")
    return _canonical(name) if name else None


def _configured_name(raw: str) -> str | None:
    """A name from .env: a Host-header form, or a bare IP address (IPv6 without brackets too)."""
    try:
        return ipaddress.ip_address(raw.strip().strip("[]")).compressed
    except ValueError:
        return host_name(raw)


def origin_key(raw: str) -> str:
    """An Origin compared as sent, case folded. Never strip a slash: "file://" would become "file:"."""
    return raw.strip().lower()


def cors_origins(environ: Mapping[str, str]) -> list[str]:
    """The browser origins CORS allows: NOVA_CORS_ALLOWED_ORIGINS, else the local Vite origins."""
    raw = (environ.get(CORS_ORIGINS_ENV) or "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return list(CORS_ALLOWED_ORIGINS_DEFAULT)


def _bind_host(environ: Mapping[str, str], warnings: list[str]) -> str | None:
    raw = environ.get(API_HOST_ENV)
    bind = DEFAULT_API_HOST if raw is None else raw.strip()
    if bind in WILDCARD_BIND_HOSTS:
        warnings.append(
            f"{API_HOST_ENV}={bind!r} listens on every interface, but a wildcard is never a Host name: "
            f"to reach the API by a LAN name or address, list it in {ALLOWED_HOSTS_ENV}"
        )
        return None
    name = _configured_name(bind)
    if name is None:
        warnings.append(f"{API_HOST_ENV}={bind!r} is not a host name; it was not added to the allowed names")
    return name


def load_policy(environ: Mapping[str, str]) -> tuple[GuardPolicy, list[str]]:
    """The policy for this process, and the startup warnings to log about it."""
    warnings: list[str] = []
    hosts = {_canonical(h) for h in NOVA_API_LOOPBACK_HOSTS}
    bind = _bind_host(environ, warnings)
    if bind:
        hosts.add(bind)
    any_host = False
    for entry in (environ.get(ALLOWED_HOSTS_ENV) or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        if entry == ALLOWED_HOSTS_ANY:
            any_host = True
            continue
        name = _configured_name(entry)
        if name is None:
            warnings.append(f"{ALLOWED_HOSTS_ENV} entry {entry!r} is not a host name and was ignored")
        else:
            hosts.add(name)
    if any_host:
        warnings.append(
            f"{ALLOWED_HOSTS_ENV}='*': the API answers to any Host name, so a web page can reach it "
            "through DNS rebinding; list the names instead"
        )
    listed = [origin_key(o) for o in cors_origins(environ)]
    ws_origins = {o for o in listed if o not in NEVER_ALLOWED_ORIGINS} | set(DESKTOP_WS_ORIGINS)
    dropped = sorted({o for o in listed if o in NEVER_ALLOWED_ORIGINS})
    if dropped:
        instead = ""
        if CORS_ANY_ORIGIN in dropped:
            # To CORS, '*' is every page, the desk's own Vite pages among them. Sockets keep
            # those, so the browser desk's fetches and feeds never part ways.
            vite = sorted(origin_key(o) for o in CORS_ALLOWED_ORIGINS_DEFAULT)
            ws_origins |= set(vite)
            instead = f"; in place of '*' they take the local Vite origins ({', '.join(vite)})"
        warnings.append(
            f"{CORS_ORIGINS_ENV} lists {', '.join(repr(o) for o in dropped)}; "
            f"sockets never take those origins (any website can send them){instead}"
        )
    return GuardPolicy(frozenset(hosts), any_host, frozenset(ws_origins)), warnings


def host_allowed(policy: GuardPolicy, name: str | None) -> bool:
    if policy.any_host:
        return True
    if name is None:
        return False
    if name in policy.hosts:
        return True
    try:
        return ipaddress.ip_address(name).is_loopback  # 127.0.0.0/8 and ::1
    except ValueError:
        return False


def origin_allowed(policy: GuardPolicy, origin: str) -> bool:
    return origin_key(origin) in policy.ws_origins


def check_request(
    policy: GuardPolicy, kind: str, hosts: Iterable[str], origins: Iterable[str]
) -> Refusal | None:
    """None when the request may pass; else why not.

    ``kind`` is the ASGI scope type. Every request needs exactly one allowed
    Host. A socket's Origin is checked too: none passes (only non-browser
    clients send none), one must be allowed, more than one is refused. An
    HTTP request's Origin is left to CORS and the API key: the packaged desk
    sends no Origin on its fetches, and an Origin rule there would lock it out.
    """
    host_values = list(hosts)
    if len(host_values) != 1 or not host_allowed(policy, host_name(host_values[0])):
        return Refusal("Host", ", ".join(host_values), REASON_HOST_NOT_ALLOWED)
    if kind != "websocket":
        return None
    origin_values = list(origins)
    if not origin_values:
        return None
    if len(origin_values) != 1 or not origin_allowed(policy, origin_values[0]):
        return Refusal("Origin", ", ".join(origin_values), REASON_ORIGIN_NOT_ALLOWED)
    return None
