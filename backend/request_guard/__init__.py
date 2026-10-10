"""Which Host names and browser origins may reach the API: the DNS-rebinding guard for every route and the cross-site guard for every WebSocket.

Every HTTP request and WebSocket handshake needs exactly one Host header naming
the API: 127.0.0.1 (any 127.x address), localhost or [::1], any port, plus the
bind host and the names in NOVA_ALLOWED_HOSTS. A web page that rebinds its own
DNS name to 127.0.0.1 still sends its own name, so it is refused (400 JSON).

A WebSocket that carries an Origin must come from a page allowed for CORS
(NOVA_CORS_ALLOWED_ORIGINS, else the local Vite origins) or from the packaged
desk (file://). A socket with no Origin (Python, Node, bots, tests) passes:
every browser sends one. HTTP Origins are left to CORS and the API key.

constants_request_guard.py (names, texts, limits), policy.py (the pure rules),
middleware.py (the ASGI middleware and its rate-limited refusal log).
Schema: architecture/schema/desk-ops.md, "Who may reach the API".
"""
from __future__ import annotations

import logging
import os
from collections.abc import Mapping

from request_guard.middleware import RequestGuardMiddleware
from request_guard.policy import GuardPolicy, cors_origins, load_policy

logger = logging.getLogger(__name__)


def configure_request_guard(app, environ: Mapping[str, str] | None = None) -> GuardPolicy:
    """Add the guard to ``app`` with a policy read now, once.

    Starlette builds middleware on the first request, so a policy read in the
    middleware's constructor would come from whatever the environment holds
    then; reading it here ties it to the moment the app is built.
    """
    policy, warnings = load_policy(os.environ if environ is None else environ)
    app.add_middleware(RequestGuardMiddleware, policy=policy)
    logger.info(
        "request guard: answers Host names %s%s; sockets take Origins %s, or none",
        ", ".join(sorted(policy.hosts)),
        " (and any 127.x address)" if not policy.any_host else " -- and ANY Host name",
        ", ".join(sorted(policy.ws_origins)),
    )
    for warning in warnings:
        logger.warning("request guard: %s", warning)
    return policy


__all__ = [
    "GuardPolicy",
    "RequestGuardMiddleware",
    "configure_request_guard",
    "cors_origins",
    "load_policy",
]
