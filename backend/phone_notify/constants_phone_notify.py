"""Names and numbers of the phone's notifications (ADR 070, amendment 2026-11-18)."""
from __future__ import annotations

NOTIFY_SCHEMA_VERSION = 1
# Settings and subscribed phones, under the operator cache (paths.cache_dir()).
NOTIFY_FILE = "phone-notify.json"
NOTIFY_API_PREFIX = "/api/phone/notify"

# The PC's sending key (the private half of its P-256 pair, base64url), one line of the desk's .env. The
# backend writes it the first time a phone asks to subscribe; a phone subscribes to its public half.
NOTIFY_KEY_ENV = "NOVA_PHONE_PUSH_KEY"
# Who a push service may contact about this sender (RFC 8292 "sub"). No mailbox of the operator's is named.
NOTIFY_SUBJECT_ENV = "NOVA_PHONE_PUSH_SUBJECT"
NOTIFY_SUBJECT_DEFAULT = "https://nova.altaystudio.com"
NOTIFY_TOKEN_SEC = 12 * 3600          # a sending token's life; the standard allows 24 hours at most

# The push services a phone's address may name, by exact host: Chrome's (Google), Firefox's, Safari's. A
# subscription to any other host is refused, and the PC posts to an address rebuilt on a name from this
# list (``sender.push_url``), so the host it contacts is never text a phone supplied.
NOTIFY_PUSH_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com")
NOTIFY_MAX_DEVICES = 4
NOTIFY_ENDPOINT_MAX_CHARS = 1024

NOTIFY_SEND_TIMEOUT_SEC = 10.0
# How long a push service keeps a notification for a phone that is off or out of signal. A market alert an
# hour late is noise; a fill or a loss limit mark is still news.
NOTIFY_TTL_MARKET_SEC = 600
NOTIFY_TTL_ACCOUNT_SEC = 6 * 3600
NOTIFY_RECORD_SIZE = 4096
NOTIFY_BODY_MAX_CHARS = 240

# Kinds of notification.
KIND_HOD = "hod_momo"
KIND_SETUP = "setup"
KIND_LEADER = "new_leader"
KIND_FILL = "fill"
KIND_LOSS_LIMIT = "loss_limit"
KIND_TEST = "test"
# The kinds the operator's hours hold back; the others come at any time.
NOTIFY_MARKET_KINDS = (KIND_HOD, KIND_SETUP, KIND_LEADER)

HOD_MODE_OFF = "off"
HOD_MODE_STARS = "stars"
HOD_MODE_ALL = "all"
HOD_MODES = (HOD_MODE_OFF, HOD_MODE_STARS, HOD_MODE_ALL)
# One HOD Momo notification per stock per quiet period: the desk's own toast rule (WATCH_TOAST_QUIET_MS).
NOTIFY_HOD_QUIET_SEC = 15 * 60.0
# A setup's stages that notify, in the order a setup climbs them.
NOTIFY_SETUP_STAGES = ("armed", "near", "triggered")

# Hours are New York time, on the half hour, inside the day the desk has prices for.
NOTIFY_TZ = "America/New_York"
NOTIFY_EARLIEST = "04:00"
NOTIFY_LATEST = "20:00"
NOTIFY_STEP_MIN = 30
# Everything starts off. The hours are the desk's own toast window's default.
NOTIFY_DEFAULT_SETTINGS = {
    "schema_version": NOTIFY_SCHEMA_VERSION,
    "hod_momo": HOD_MODE_OFF,
    "setups": False,
    "new_leader": False,
    "fills": False,
    "loss_limit": False,
    "days": [0, 1, 2, 3, 4],
    "start": "07:00",
    "end": "16:00",
}

# Venues whose account events notify. A Sim replay is another day's market: its fills and marks never do.
NOTIFY_ACCOUNT_VENUES = ("live", "paper")

REASON_NO_KEY = "PHONE_NOTIFY_NO_KEY"
REASON_BAD_ADDRESS = "PHONE_NOTIFY_BAD_ADDRESS"
REASON_BAD_SETTINGS = "PHONE_NOTIFY_BAD_SETTINGS"
REASON_NO_DEVICE = "PHONE_NOTIFY_NO_DEVICE"
REASON_TOO_MANY = "PHONE_NOTIFY_TOO_MANY"
REASON_SEND_FAILED = "PHONE_NOTIFY_SEND_FAILED"
