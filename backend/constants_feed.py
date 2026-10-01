"""Is IBKR data arriving? The feed's heartbeat and its gaps (#672, #673). Owner: ``ibkr/feed_pulse.py``."""

FEED_PULSE_SCHEMA_VERSION = 1

# A gap: no IBKR market-data message on any line for this long, after a busy stretch.
# 2026-10-01 09:31-09:32 ET: the desk's Wi-Fi re-authenticated five times and the feed
# went silent for 4, 4, 8, 16 and 4 s; a busy feed delivers something every ~0.1 s.
FEED_GAP_SEC = 3.0
# "Busy": data arrived in at least this share of the whole seconds in the window
# before the silence, not counting seconds inside an earlier gap. A thin after-hours
# feed that is quiet for seconds at a time never reads as a gap.
FEED_GAP_BUSY_WINDOW_SEC = 10
FEED_GAP_BUSY_FRACTION = 0.8
FEED_GAP_BUSY_MIN_SEC = 3  # fewer known seconds than this: not enough to call the feed busy
# After a gap IBKR delivers everything it held in one burst, stamped on arrival
# (#563): 722 L1 events in the second after the 16 s silence against ~130 before.
# Tape reads treat that long after the first message as still the gap's (#673).
FEED_GAP_SETTLE_SEC = 5.0
FEED_DIAG_WINDOW_SEC = 1800.0  # closed gaps this recent make the checklist row warn
FEED_GAP_KEEP = 50          # closed gaps kept in memory, newest last
FEED_GAP_SECONDS_KEEP = 64  # whole seconds with data kept for the busy rule
# The extended session (Eastern) on exchange days. Outside it a silent feed is the
# market closing, never a gap.
FEED_SESSION_START_ET = (4, 0)
FEED_SESSION_END_ET = (20, 0)

# Wi-Fi attribution: Windows' WLAN AutoConfig log, read-only (``ibkr/wifi_drops.py``).
WIFI_LOG = "Microsoft-Windows-WLAN-AutoConfig/Operational"
WIFI_EVENT_SECURITY_STOPPED = 11004  # "Wireless security stopped": the link is down
WIFI_EVENT_SECURITY_SUCCEEDED = 11005  # "Wireless security succeeded": back
WIFI_LOOKBACK_SEC = 15.0   # a drop that began this long before the silence still explains it
WIFI_REREAD_SEC = 3.0      # an open gap's Wi-Fi read is refreshed at most this often
WIFI_WEVTUTIL_TIMEOUT_SEC = 5.0
WIFI_WEVTUTIL_MAX_EVENTS = 60
WIFI_CACHE_KEEP = 64       # gaps whose Wi-Fi reads are kept
