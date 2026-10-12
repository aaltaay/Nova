"""The market data front door's library: what the operator's Massive files and Nova's stores hold, and one stock-day
out of them as a table. ``tools/market_data.py`` is its command line; ``docs/market-data.md`` is the catalog.

Read-only on the data. The one thing it writes is the seek indexes ``backend/sim/massive_index.py`` owns
(``inventory.build_indexes``), the same files the Sim's own reader builds and reads.

From Python (repo root on ``sys.path``)::

    import sys; sys.path.insert(0, "research")
    from market_reads import reads
    trades = reads.trades("GME", "2021-01-27", "09:30", "09:35")      # a pandas DataFrame
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "backend") not in sys.path:
    sys.path.insert(0, str(REPO / "backend"))
