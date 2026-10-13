"""How close Nova's LULD bands came to the exchanges' when last measured (ADR 047).

Measured with ``py -3 tools/luld_check.py massive`` (``luld/study.py``) over the Massive flat files. Each
row is a moment the SIP flagged the national best bid on the upper band (or the best offer on the lower),
compared with Nova's band then, from the same trades and NBBO. Counted: the stocks the Nasdaq halt log
paused, with a previous close the day aggregates can be trusted for (no split) and under $50 (Tier 2).
The desk quotes this beside the line, so an estimate is never styled as the exchanges' own. Re-measure
after a change to ``tracker.py``.

``backfill`` is the band of a stock Nova began watching mid-session, rebuilt from IBKR's trades before it
(ADR 047 amendment 2026-10-13): ``py -3 tools/luld_check.py backfill`` (``luld/backfill_study.py``, variant
``hybrid_4000``) on the same days, a tracker started 30 s to 4 minutes before each touch where waiting for
Nova's own tape showed no band. Where four pages ran short, the bars that filled in were measured at their best
(each minute's own mean of trades); IBKR's are volume-weighted.
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
    "backfill": {
        "measured": "2026-10-13",
        "touches": 1803,
        "exact": 869,
        "within_1c": 1149,
        "inside_spread": 1586,
        "text": ("a band rebuilt from IBKR's trades matched the exchanges' to the cent on 48% of 1,803 band touches "
                 "30 s to 4 minutes after Nova began watching, within 1c on 64% and within its stated spread on "
                 "88% (10 trading days, 2026-09-22 to 10-05)"),
    },
}
