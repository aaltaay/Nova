"""The market data front door's library: what the operator's Massive files, Nova's stores, Massive's reference dump
and SEC's bulk files hold, as tables, each as known on a past day (ADR 059). ``tools/market_data.py`` is its command
line, ``tools/nova_data_mcp.py`` its MCP server, ``catalog.py`` the list, ``docs/market-data.md`` the prose.

Read-only on the data. It writes three derived things: the seek indexes ``backend/sim/massive_index.py`` owns
(``inventory.build_indexes``), the same files the Sim's own reader builds and reads, the reference dump's
index ``reference.py`` owns (``store/reference_index.sqlite3``), and the parsed stock-days ``read_cache.py`` keeps.

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
