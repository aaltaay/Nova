"""Pre-broker validation for the centralized execution path."""
from __future__ import annotations

from execution.models import ExecutionCommand
from ibkr import account as _account
from ibkr import client as _client
from ibkr import safety as _safety


def validate_command(cmd: ExecutionCommand) -> tuple[bool, str, str | None]:
    """Return (ok, detail, reason_code). Pure structural + safety gates."""
    if not cmd.idempotency_key or not str(cmd.idempotency_key).strip():
        return False, "idempotency_key is required", "IDEMPOTENCY_MISSING"

    if cmd.operation == "cancel":
        if cmd.order_id is None:
            return False, "order_id required for cancel", "ORDER_ID_MISSING"
        ok, reason = _safety.assert_cancel_allowed(
            client_enabled=_client.is_enabled(),
            connected=_client.is_connected(),
        )
        if not ok:
            return False, reason, "CANCEL_GATE"
        return True, "OK", None

    if cmd.operation == "replace":
        if cmd.order_id is None:
            return False, "order_id required for replace", "ORDER_ID_MISSING"
        if cmd.limit_price is None and cmd.stop_price is None:
            return False, "replace requires limit_price or stop_price", "REPLACE_PRICE_MISSING"
        if cmd.side is not None or cmd.qty is not None or cmd.symbol is not None:
            # Callers must not attempt to mutate immutable fields via replace.
            pass
        ok, reason = _safety.assert_orders_allowed(
            client_enabled=_client.is_enabled(),
            connected=_client.is_connected(),
            account_mode=_client.account_mode(),
            broker_account_kind=_client.broker_account_kind(),
        )
        if not ok:
            return False, reason, "ORDERS_GATE"
        return True, "OK", None

    symbol = cmd.normalized_symbol()
    if not symbol:
        return False, "symbol is required", "SYMBOL_MISSING"
    if cmd.operation == "place":
        if cmd.side not in ("BUY", "SELL"):
            return False, "side must be BUY or SELL", "SIDE_INVALID"
        qty = float(cmd.qty or 0)
        if qty <= 0:
            return False, "qty must be greater than zero", "QTY_INVALID"
        if cmd.order_type not in ("MKT", "LMT", "STP"):
            return False, "order_type must be MKT, LMT, or STP", "ORDER_TYPE_INVALID"
        if cmd.order_type == "LMT" and (cmd.limit_price is None or cmd.limit_price <= 0):
            return False, "limit_price required for LMT", "LIMIT_MISSING"
        if cmd.order_type == "STP" and (cmd.stop_price is None or cmd.stop_price <= 0):
            return False, "stop_price required for STP", "STOP_MISSING"
        if cmd.outside_rth and cmd.order_type == "STP":
            return False, "outside_rth is not supported for STP", "OUTSIDE_RTH_INVALID"
    elif cmd.operation == "bracket":
        if cmd.entry_price is None or cmd.stop_price is None or cmd.target_price is None:
            return False, "bracket requires entry/stop/target", "BRACKET_FIELDS"
        shares = int(cmd.shares or cmd.qty or 0)
        if shares <= 0:
            return False, "bracket qty/shares must be > 0", "QTY_INVALID"
    else:
        return False, f"unknown operation: {cmd.operation}", "OP_INVALID"

    ok, reason = _safety.assert_orders_allowed(
        client_enabled=_client.is_enabled(),
        connected=_client.is_connected(),
        account_mode=_client.account_mode(),
        broker_account_kind=_client.broker_account_kind(),
    )
    if not ok:
        return False, reason, "ORDERS_GATE"
    return True, "OK", None


def check_account_and_position(cmd: ExecutionCommand) -> tuple[bool, str, str | None]:
    """Cached account/position checks. Fail closed when data is incomplete for spends."""
    if cmd.operation in ("cancel",):
        return True, "OK", None

    if not _client.is_connected():
        return False, "account checks require IBKR connection", "ACCOUNT_UNAVAILABLE"

    summary = _account.get_account_summary()
    # Prefer live summary when present; if the cache is empty/pending, fail closed
    # only for priced BUY notions (market orders cannot estimate notional).
    bp = summary.get("BuyingPower") if summary.get("connected") else None

    if cmd.operation in ("place", "bracket") and cmd.source not in ("flatten", "kill"):
        if cmd.operation == "place" and (cmd.side or "").upper() == "BUY":
            est = _estimate_notional(cmd)
            if bp is None and summary.get("pending") and est is not None:
                return False, "BuyingPower not yet available — refuse spend", "BUYING_POWER_UNKNOWN"
            if bp is not None and est is not None and est > float(bp):
                return False, f"estimated notional {est:.2f} exceeds BuyingPower {bp}", "BUYING_POWER"

        if cmd.operation == "place" and (cmd.side or "").upper() == "SELL":
            # Position-reducing sells (flatten/close) are allowed; opening a short is not.
            if cmd.source not in ("flatten",):
                pos_qty = _position_qty(cmd.normalized_symbol() or "")
                sell_qty = float(cmd.qty or 0)
                if pos_qty is None or pos_qty <= 0:
                    return False, "SELL refused — no long position to reduce", "NO_POSITION"
                if sell_qty > pos_qty + 1e-6:
                    return False, f"SELL qty {sell_qty} exceeds position {pos_qty}", "OVERSELL"

    return True, "OK", None


def _estimate_notional(cmd: ExecutionCommand) -> float | None:
    qty = float(cmd.qty or cmd.shares or 0)
    if qty <= 0:
        return None
    px = cmd.limit_price or cmd.entry_price
    if px is None or px <= 0:
        return None  # market — cannot estimate; skip BP numeric compare
    return qty * float(px)


def _position_qty(symbol: str) -> float | None:
    for p in _account.get_positions():
        if str(p.get("symbol") or "").upper() == symbol.upper():
            try:
                return float(p.get("qty") or 0)
            except (TypeError, ValueError):
                return None
    return None
