"""Which Host names and browser origins may reach the API. Owner: backend/request_guard/.

The loopback names themselves are not redefined here: they are
``NOVA_API_LOOPBACK_HOSTS`` (constants_nova_os) and the bind default is
``api_process_guard.DEFAULT_API_HOST``.
"""
from __future__ import annotations

# Extra Host names the API answers to, comma-separated, a port ignored. Empty by
# default: the API answers only on loopback names. '*' turns the Host check off
# (not recommended: a web page can then reach the API through DNS rebinding).
ALLOWED_HOSTS_ENV = "NOVA_ALLOWED_HOSTS"
ALLOWED_HOSTS_ANY = "*"
# The bind host (run_api.py). Its own name is allowed unless it is a wildcard.
API_HOST_ENV = "NOVA_API_HOST"
# One knob for "a page at this origin may use the API": CORS for its fetches and
# this guard for its sockets read the same list (request_guard.policy.cors_origins).
CORS_ORIGINS_ENV = "NOVA_CORS_ALLOWED_ORIGINS"

# A wildcard bind listens on every interface but is never a Host name a client sends.
WILDCARD_BIND_HOSTS = ("", "0.0.0.0", "::", "[::]")

# Nova's packaged desk loads its page with loadFile(), and Electron 41 sends
# Origin "file://" on that page's sockets (measured 2026-10-09 on Electron
# 41.10.6 / Chromium 146; its fetches send no Origin at all). Browsers send
# "null" for a local file, so no website can send "file://".
DESKTOP_WS_ORIGINS = ("file://",)
# "*" in the CORS list: CORS lets every page's fetches through.
CORS_ANY_ORIGIN = "*"
# Never a socket origin, even when listed for CORS: "null" is what sandboxed
# iframes on any website send, and "*" is not an origin. With "*" listed, sockets
# take the local Vite origins in its place (policy.load_policy), so the browser
# desk keeps its feeds while no other page gets them.
NEVER_ALLOWED_ORIGINS = ("null", CORS_ANY_ORIGIN)

# A Host header longer than a DNS name can be is refused unread.
HOST_HEADER_MAX_CHARS = 255
# Parsed Host headers kept (policy.host_name): a desk sends one or two; any value churns it, never grows it.
HOST_NAME_CACHE_SIZE = 64

HOST_REFUSED_STATUS = 400
# A socket refused before accept, when the server can send an HTTP answer
# (the ASGI websocket.http.response extension: uvicorn 0.44 and TestClient).
WS_REFUSED_HTTP_STATUS = 403
# A socket refused before accept otherwise: close code 1008, policy violation.
WS_POLICY_VIOLATION = 1008

REASON_HOST_NOT_ALLOWED = "HOST_NOT_ALLOWED"
REASON_ORIGIN_NOT_ALLOWED = "ORIGIN_NOT_ALLOWED"

HOST_REFUSED_DETAIL = (
    "Nova's API does not answer to this Host name. It answers on 127.0.0.1, localhost "
    "and [::1]; to reach it by another name, add the name to NOVA_ALLOWED_HOSTS in .env "
    "and restart the API."
)
ORIGIN_REFUSED_DETAIL = (
    "Nova's API does not open sockets for pages at this origin. The desk's own origins "
    "are allowed; to open sockets from another page, add its origin to "
    "NOVA_CORS_ALLOWED_ORIGINS in .env and restart the API."
)
# A WebSocket close reason must fit in 123 bytes.
WS_CLOSE_REASON_HOST = "Host not allowed: add it to NOVA_ALLOWED_HOSTS"
WS_CLOSE_REASON_ORIGIN = "Origin not allowed: add it to NOVA_CORS_ALLOWED_ORIGINS"

# One WARNING per refused (kind, header, value) per window; the refusals in
# between are counted on the next line. The key map is cleared when it grows
# past the cap, so values an attacker varies cannot grow memory.
REFUSAL_LOG_WINDOW_SEC = 60.0
REFUSAL_LOG_KEYS_MAX = 256
LOGGED_VALUE_MAX_CHARS = 200

# The recent refusals the desk diagnostics row reads (recent_refusals.py, #828 item 1):
# one entry per refused (kind, header, value), the least recently seen dropped past
# the cap, so values an attacker varies cannot grow memory. Values and paths are cut
# to LOGGED_VALUE_MAX_CHARS, as in the log.
RECENT_REFUSALS_MAX = 32

# The diagnostics row (diagnostics/collect_request_guard.py): yellow while the latest
# refusal is this recent, then back to OK with "last refused N min ago", so one probe
# does not keep the desk yellow all day.
REFUSAL_DIAG_RECENT_SEC = 15 * 60
# The row names refused values only in its fix, never in its detail or cause, which
# an issue filed from the desk copies into a public page. The fix names the latest
# value of each kind of refusal, then at most this many others, most recent first;
# the rest are counted.
REFUSAL_DIAG_VALUES_SHOWN = 3
# A refused value is attacker-controlled text: the fix shows this much of it,
# its unprintable characters as "?". The evidence keeps the stored value.
REFUSAL_DIAG_VALUE_SHOWN_MAX_CHARS = 60
# Named in the row's fix for a Host refusal: a Host name opened to another machine
# also needs the API on that interface and a key on its writes (auth.py reads it).
API_KEY_ENV = "NOVA_API_KEY"
