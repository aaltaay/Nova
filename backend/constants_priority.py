"""The trading path's scheduling priority (ADR 045). Owner: ``process_priority/``.

2026-10-05: the backend and IB Gateway ran at BelowNormal -- inherited from a scheduled task and
kept across every restart -- while builds, browsers and agents ran at Normal on the same PC.
"""

# Each known process is read again this often, and raised when found lower: other software on the
# desk PC lowers processes after they start (2026-10-05: the API logged Normal at 14:17:12 and read
# BelowNormal minutes later; explorer.exe and everything it started ran BelowNormal).
PROCESS_PRIORITY_RECHECK_SEC = 2.0
# The Gateway and IBC's launch loop are looked for again this often (IBC relaunches the Gateway at
# its nightly restart; a process list is tens of ms, so not every recheck).
PROCESS_PRIORITY_DISCOVER_SEC = 30.0
# A demotion is logged at WARNING once per process and this often after (each is counted).
PROCESS_PRIORITY_WARN_EVERY_SEC = 600.0

# Off with NOVA_PROCESS_PRIORITY=0 (Windows only; nothing to do elsewhere).
PROCESS_PRIORITY_ENV = "NOVA_PROCESS_PRIORITY"

# The IBC launch chain above the Gateway's java.exe (its relaunch inherits from it), by command line.
PROCESS_PRIORITY_IBC_PATTERN = r"(?i)\\IBC\\|StartGateway|start_gateway|DisplayBannerAndLaunch|ibcstart"
PROCESS_PRIORITY_IBC_MAX_DEPTH = 4
