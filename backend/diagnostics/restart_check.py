"""What a restart of this API process would interrupt now (ADR 038 amendment, 2026-09-29).

``GET /api/diagnostics/restart-check``. The desk reads it before "Restart backend now" and lists
what is open; the nightly sync restarts the backend only when ``safe`` is true. Memory reads only
-- no network and no IBKR request: the Session Records, the practice ledgers this process has
loaded, IBKR's cached positions and open orders, the bot's trade, the stock modes held in memory
(ADR 037) and the history downloads running. A reader that fails is named in ``unknown``; it is
never read as "nothing open", so ``safe`` is null (not true) until every reader answered.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from constants_diagnostics import (
    DIAG_RESTART_APPROVAL_OPEN,
    DIAG_RESTART_BOT_TRADE_OPEN,
    DIAG_RESTART_CHECK_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)

Item = dict[str, Any]
Reader = Callable[[], list[Item]]
_EPS = 1e-9


def _item(kind: str, text: str, *, venue: str | None = None, symbol: str | None = None) -> Item:
    return {"kind": kind, "venue": venue, "symbol": symbol, "text": text}


def _qty(value: Any) -> str:
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return "?"


def order_text(row: dict[str, Any]) -> str:
    """``SELL 100 APUS LMT 4.96`` from an order row (practice and IBKR rows share the shape)."""
    qty = row.get("remaining_qty") if row.get("remaining_qty") not in (None, 0) else row.get("qty")
    parts = [str(row.get("side") or "?"), _qty(qty), str(row.get("symbol") or "?"), str(row.get("order_type") or "")]
    for key in ("limit_price", "stop_price"):
        if row.get(key) is not None:
            parts.append(f"{float(row[key]):g}")
            break
    return " ".join(p for p in parts if p)


def recordings() -> list[Item]:
    from capture.mode import capture_symbols

    return [
        _item("recording", f"Recording {sym}: a few seconds' gap, then it resumes on its own", symbol=sym)
        for sym in capture_symbols()
    ]


def practice() -> list[Item]:
    """Paper and Sim, as far as this process has loaded them (an unloaded ledger has nothing running)."""
    from practice.broker import loaded

    items: list[Item] = []
    for venue, label, effect_pos, effect_order in (
        ("paper", "Paper", "Nova stops watching it while the backend restarts",
         "it cannot fill while the backend restarts"),
        ("sim", "Sim", "the Sim scratch account starts over after a restart",
         "the Sim scratch account starts over after a restart"),
    ):
        broker = loaded(venue)
        if broker is None:
            continue
        for row in broker.ledger.position_rows():
            sym = str(row.get("symbol") or "?")
            items.append(_item("position", f"{label} position {sym} {_qty(row.get('qty'))}: {effect_pos}",
                               venue=venue, symbol=sym))
        for row in broker.working_orders():
            items.append(_item("working_order", f"{label} working order {order_text(row)}: {effect_order}",
                               venue=venue, symbol=str(row.get("symbol") or "") or None))
    return items


def ibkr() -> list[Item]:
    """IBKR's cached account. No ready session means Nova watches nothing there: a restart changes nothing."""
    from ibkr import client
    from ibkr.order_rows import trade_to_order_row

    ib = client.get_ib()
    if ib is None:
        return []
    items: list[Item] = []
    for pos in ib.positions():
        qty = float(pos.position or 0)
        if abs(qty) < _EPS:
            continue
        sym = str(pos.contract.symbol)
        items.append(_item(
            "position", f"IBKR position {sym} {qty:g}: IBKR keeps it; the desk's view of it pauses",
            venue="ibkr", symbol=sym,
        ))
    for trade in ib.openTrades():
        row = trade_to_order_row(trade)
        items.append(_item(
            "working_order", f"IBKR working order {order_text(row)}: IBKR keeps it working",
            venue="ibkr", symbol=str(row.get("symbol") or "") or None,
        ))
    return items


def bot_trade() -> list[Item]:
    from bot.session import raw

    trade = raw().get("trade")
    if not isinstance(trade, dict) or trade.get("state") not in DIAG_RESTART_BOT_TRADE_OPEN:
        return []
    sym = str(trade.get("symbol") or "?")
    return [_item(
        "bot_trade", f"Bot trade {sym} ({trade.get('state')}): its stop watch pauses; it resumes after the restart",
        venue=str(trade.get("venue") or "") or None, symbol=sym,
    )]


def stock_modes() -> list[Item]:
    """ADR 037's store lives in memory: a restart returns every stock to Signal only."""
    from constants_stock_mode import (
        STOCK_MODE_SIDE_NOVA,
        STOCK_MODE_TRADE_ENTERING,
        STOCK_MODE_TRADE_HOLDING,
    )
    from stock_mode import store

    items: list[Item] = []
    for sym, row in sorted(store.switches().items()):
        if STOCK_MODE_SIDE_NOVA in (row.get("buy"), row.get("sell")):
            items.append(_item(
                "stock_mode", f"{sym} is set to Buy {row.get('buy')} / Sell {row.get('sell')}: "
                "a restart returns it to Signal only", symbol=sym,
            ))
    for sym, row in sorted(store.approvals().items()):
        if row.get("state") in DIAG_RESTART_APPROVAL_OPEN:
            items.append(_item(
                "stock_mode", f"Approval on {sym} ({row.get('state')}): a restart withdraws it", symbol=sym,
            ))
    for row in store.trades():
        if row.get("state") in (STOCK_MODE_TRADE_ENTERING, STOCK_MODE_TRADE_HOLDING):
            sym = str(row.get("symbol") or "?")
            items.append(_item(
                "stock_mode", f"Nova's {row.get('kind')} trade on {sym} ({row.get('state')}): a restart forgets it",
                venue=str(row.get("venue") or "") or None, symbol=sym,
            ))
    return items


def downloads() -> list[Item]:
    from sim.history_download import running_ids

    count = len(running_ids())
    if not count:
        return []
    noun = "download" if count == 1 else "downloads"
    return [_item("download", f"{count} history {noun} running: a restart interrupts it; start it again after")]


READERS: tuple[tuple[str, Reader], ...] = (
    ("recording", recordings),
    ("practice", practice),
    ("ibkr", ibkr),
    ("bot_trade", bot_trade),
    ("stock_mode", stock_modes),
    ("download", downloads),
)


def restart_check(readers: tuple[tuple[str, Reader], ...] | None = None, now: float | None = None) -> dict[str, Any]:
    """``{schema_version, generated_at, safe, open[], unknown[]}``.

    ``safe`` is true only when every reader answered and nothing is open, false when something is
    open, and null when nothing was found but a reader could not answer.
    """
    open_items: list[Item] = []
    unknown: list[dict[str, str]] = []
    for kind, read in READERS if readers is None else readers:
        try:
            open_items.extend(read())
        except Exception as exc:  # a failed read is stated, never "nothing open"
            logger.warning("restart check: could not read %s: %s", kind, exc, exc_info=True)
            unknown.append({"kind": kind, "error": f"{type(exc).__name__}: {exc}"})
    safe: bool | None = False if open_items else (None if unknown else True)
    return {
        "schema_version": DIAG_RESTART_CHECK_SCHEMA_VERSION,
        "generated_at": time.time() if now is None else now,
        "safe": safe,
        "open": open_items,
        "unknown": unknown,
    }
