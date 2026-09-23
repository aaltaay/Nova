"""Tunables for explaining why IB Gateway needed a full login (#14).

Owners: ``ibkr/windows_restarts.py`` (reads Windows restart and sign-in
events) and ``ibkr/relogin_reason.py`` (pure explanation). Consumers: the
diagnostics Gateway rows and ``tools/premarket_verify.py``.
"""
from __future__ import annotations

# A restart counts as the reason for a full login only when the PC booted at
# most this long before that login. The Gateway's own 11:45 PM restart
# re-uses the saved login every night, so a boot older than a day cannot be
# what cost it.
RELOGIN_BOOT_WINDOW_SEC = 24 * 3600

# Restart events (System 1074) up to this long before a boot belong to that
# boot. Windows Update often restarts twice in a row; the earliest event in
# the window names who started the chain.
RELOGIN_RESTART_CHAIN_SEC = 30 * 60

# Boots closer together than this are one restart (the update's second
# reboot), reported once with the first boot's cause.
RELOGIN_BOOT_MERGE_SEC = 15 * 60

# An unexpected-shutdown record (System 6008) is written when the event log
# starts after the boot; allow this much slack between the two.
RELOGIN_UNEXPECTED_AFTER_BOOT_SEC = 10 * 60

# A first sign-in this long after the boot is worth saying: until someone
# signs in, Nova's scheduled tasks (Interactive logon type) do not run.
RELOGIN_SIGNIN_GAP_NOTE_SEC = 15 * 60

# ``wevtutil`` is read-only, but it is a process start: cap it.
RELOGIN_WEVTUTIL_TIMEOUT_SEC = 8.0
RELOGIN_WEVTUTIL_MAX_EVENTS = 400

# Restart initiators, by executable basename (lower case) -> plain label.
RELOGIN_WINDOWS_UPDATE_PROCESSES = frozenset({
    "mousocoreworker.exe",
    "trustedinstaller.exe",
    "usoclient.exe",
    "tiworker.exe",
    "wuauclt.exe",
    "musnotification.exe",
    "musnotificationux.exe",
})
RELOGIN_START_MENU_PROCESSES = frozenset({
    "startmenuexperiencehost.exe",
    "explorer.exe",
    "winlogon.exe",
})

# Premarket evidence (#14): the unattended NovaMorningCheck run fires at
# 03:55 local (the desk runs on Eastern time). A run whose first line lands in
# this window was started by the scheduler, not by hand.
PREMARKET_CHECK_WINDOW_START = "03:50"
PREMARKET_CHECK_WINDOW_END = "04:05"
PREMARKET_EVIDENCE_DAYS_DEFAULT = 7

# IBC names its log after the weekday it reads from ``wmic``, which Windows 11
# no longer ships -- every log became ``..._.txt`` and each cold start deleted
# the last one, so a week of login history could not exist. IBC keeps an
# inherited DAYOFWEEK when ``wmic`` prints nothing, so Nova sets it on every
# launch it makes.
IBC_DAYOFWEEK_ENV = "DAYOFWEEK"
