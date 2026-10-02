"""Today's hot list (ADR 043): the stocks Nova watches all day and may trade."""
from __future__ import annotations

HOT_LIST_SCHEMA_VERSION = 1
HOT_LIST_FILE = "hot-list.json"            # in the operator cache
HOT_LIST_DAY_DIR = "hot-list"              # one read-only copy per day, for the triggers audit
HOT_LIST_CAP = 20                          # CHOSEN (operator, 2026-10-01): "Day list, fresh at 04:00 ... up to 20"
HOT_LIST_AUTO_N_CHOICES = (0, 3, 5, 10)    # 0 is off
HOT_LIST_AUTO_N_DEFAULT = 5                # CHOSEN: "top 5 or 10 ... top 3"; the sketch the operator approved used 5
HOT_LIST_AUTO_START_ET = "07:00"           # the leaders rule's own start (ADR 041)
HOT_LIST_AUTO_END_ET = "16:00"             # the regular session's close
HOT_LIST_AUTO_TICK_SEC = 30.0
HOT_LIST_SIDES = ("you", "nova")
HOT_LIST_DEFAULT_SIDE = "you"              # new names start as Buy You, Sell You (operator, 2026-10-01)

HOT_LIST_FULL = "HOT_LIST_FULL"
HOT_LIST_INVALID = "HOT_LIST_INVALID"
HOT_LIST_NOVA_TRADE = "HOT_LIST_NOVA_TRADE"
HOT_LIST_UNREADABLE = "HOT_LIST_UNREADABLE"
