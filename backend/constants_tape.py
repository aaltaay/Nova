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
