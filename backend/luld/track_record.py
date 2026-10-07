"""How close Nova's LULD bands came to the exchanges' when last measured (ADR 047).

Measured with ``py -3 tools/luld_check.py massive`` (``luld/study.py``) over the Massive flat files. Each
row is a moment the SIP flagged the national best bid on the upper band (or the best offer on the lower),
compared with Nova's band then, from the same trades and NBBO. Counted: the stocks the Nasdaq halt log
paused, with a previous close the day aggregates can be trusted for (no split) and under $50 (Tier 2).
The desk quotes this beside the line, so an estimate is never styled as the exchanges' own. Re-measure
after a change to ``tracker.py``.
"""
from __future__ import annotations

TRACK_RECORD: dict = {
    "source": "the SIP's own LULD flags in the Massive flat files",
    "measured": "2026-10-06",
    "days": 10,
    "first_day": "2026-09-22",
    "last_day": "2026-10-05",
    "ticker_days": 166,
    "touches": 593,
    "exact": 480,
    "within_1c": 513,
    "within_5c": 551,
    "approx_touches": 152,
    "approx_inside_spread": 126,
    "text": ("matched the exchanges' band to the cent on 81% of 593 band touches, within 1c on 87% and within "
             "5c on 93% (10 trading days, 2026-09-22 to 10-05); an approximate band was within its stated spread "
             "on 126 of 152"),
}
