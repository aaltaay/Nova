"""Today's hot list (ADR 044, amended 2026-10-06): the stocks Nova watches all day. Who trades a stock is its
own Buy / Sell switch (ADR 037), never the list."""
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
# The feed adds a name once a day: after a restart it reads back that day's adds from the audit stream's
# tail, from this many bytes, growing the window until it reaches the day's 04:00 start.
HOT_LIST_AUTO_SEED_BYTES = 1 << 20

HOT_LIST_FULL = "HOT_LIST_FULL"
HOT_LIST_INVALID = "HOT_LIST_INVALID"
HOT_LIST_UNREADABLE = "HOT_LIST_UNREADABLE"

# How a name came onto the list, and the one board the auto feed reads.
HOT_LIST_HOW_AUTO = "auto"
HOT_LIST_HOW_STAR = "star"
HOT_LIST_HOWS = (HOT_LIST_HOW_AUTO, HOT_LIST_HOW_STAR)
HOT_LIST_BOARD_GAINERS = "gainers"
# A ticker as the desk's watch list accepts it (12 characters at most, like a stock-mode symbol).
HOT_LIST_SYMBOL_RE = r"^[A-Z][A-Z0-9./-]{0,11}$"
HOT_LIST_DATE_RE = r"^\d{4}-\d{2}-\d{2}$"

# Every change is a line on the bot's audit stream: ``action`` this, ``inputs.event`` one of the events.
HOT_LIST_AUDIT_ACTION = "hot_list"
HOT_LIST_EVENT_ROLLOVER = "rollover"       # 04:00 ET: a fresh list, and yesterday's bot buys reset
HOT_LIST_EVENT_AUTO = "auto"               # the auto feed added a leader
HOT_LIST_EVENT_STAR = "star"               # a star: the operator, or bring-back
HOT_LIST_EVENT_REMOVE = "remove"           # off the list (who trades the stock is unchanged)
HOT_LIST_EVENT_SETTINGS = "settings"       # auto_n changed
# Who starred a name (``inputs.by`` on a star line).
HOT_LIST_BY_OPERATOR = "operator"
HOT_LIST_BY_BRING_BACK = "bring_back"

# HOD Momo's active set admits the stocks the bot buys first (Buy set to the bot on the desk's venue), then
# listed names, into the reserved block they share with Former Momo (``HOD_MOMO_FORMER_MOMO_MAX_SLOTS``;
# ``hod_momo_active.build_active_set``), under these reasons.
BOT_BUY_ACTIVE_REASON = "bot_buy"
BOT_BUY_ACTIVE_OVER_RESERVED = "bot_buy_over_reserved"     # past the reserved block: not followed
BOT_BUY_ACTIVE_L1_BLOCKED = "bot_buy_l1_blocked"           # IBKR could not open its L1 line (a cooldown)
HOT_LIST_ACTIVE_REASON = "hot_list"
HOT_LIST_ACTIVE_OVER_RESERVED = "hot_list_over_reserved"   # listed past the reserved block: not followed
HOT_LIST_ACTIVE_L1_BLOCKED = "hot_list_l1_blocked"         # IBKR could not open its L1 line (a cooldown)
