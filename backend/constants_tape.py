"""The consolidated tape: which prints set a price (owner ``sale_conditions.py``).

CTA / UTP sale-condition codes whose trades are reported for volume but never
move the consolidated high, low or last. IBKR sends them in AllLast
``specialConditions`` as a positional string (``" 4 W"``, ``"  TI"``), so a
code is one character wherever it sits.

    C cash sale              H price variation        I odd lot
    M official close         N next day               P prior reference price
    Q official open          R seller                 U extended hours, out of sequence
    V contingent             W average price          4 derivatively priced
    7 qualified contingent   9 corrected consolidated close

``T`` (Form T, extended hours) is not here: extended-hours candles are drawn,
as every chart draws them. ``P`` and ``4`` go beyond the SIP high / low matrix
because IBKR's own TRADES bars leave them out (GRML 2026-09-22: a ``P`` print
$2.31 and a ``4`` print $0.60 under the market were absent from IBKR's bars).
"""
from __future__ import annotations

TAPE_NO_PRICE_CONDITIONS: frozenset[str] = frozenset("CHIMNPQRUVW479")

# IBKR's Last (tick 4) and delayed Last (68) -- reportable trades only. RTVolume
# (48) carries unreported trades too, and ib_async writes both, plus every
# AllLast print, into the one ``ticker.last`` it keeps per contract.
IBKR_LAST_TICK_TYPES: frozenset[int] = frozenset({4, 68})

# A live tape line with no print this long reads silent on the Trader's Time & Sales
# (``ibkr/tape_silence.py``, #722): amber while its Level 2 line delivered a book within
# TAPE_SILENT_BOOK_FRESH_SEC ("the tape line may be down"), plain when the book is quiet too.
# Saying so is cheap, so it is far shorter than the recorder's own re-ask (CAPTURE_TAPE_STALE_SEC).
TAPE_SILENT_SEC = 30.0
TAPE_SILENT_BOOK_FRESH_SEC = 10.0
# Dead, not quiet: the symbol's Level 1 line reported a trade (IBKR's Last Timestamp, tick 45,
# or RTVolume's trade time, 233) at least this long after the line's last print by IBKR's own
# second (#722). On 2026-10-05 SAIQ's Level 1 counted 2.5M shares in the 332 s its tape printed
# nothing, VEEA's 1.05M in 574 s. Both clocks are IBKR's, in whole seconds, so a few is enough.
TAPE_DEAD_L1_LEAD_SEC = 3.0
# Lines whose last prints arrived this close together and that are all still silent went
# silent together: one pipeline event (SAIQ and VEEA stopped at the same 09:35:42.388 arrival).
TAPE_PIPELINE_SAME_SEC = 1.0

# A tape-built 10-second candle is keyed by IBKR's own second (``exchange_ts``) and closes
# this long after its ten seconds on the desk's clock, so a print that arrives late still
# lands in it (#721: arrival trails IBKR's second by 0.6 s at the median, up to 9 s, 2026-10-05).
TAPE_10SEC_FLUSH_GRACE_SEC = 10.0
