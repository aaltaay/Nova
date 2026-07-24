"""Pre-broker validation for the centralized execution path."""
from __future__ import annotations

import logging
import math

from constants import IBKR_FRACTIONAL_ORDER_API_MSG
from execution.models import ExecutionCommand
from ibkr import account as _account
from ibkr import client as _client
from ibkr import safety as _safety
from ibkr.errors import IbkrAccountError

logger = logging.getLogger(__name__)

# Float dust below this is treated as a whole share (1.0000000001 → whole).
_WHOLE_SHARE_EPS = 1e-9


def is_whole_share_qty(qty: float) -> bool:
    """True when qty is a positive whole-share lot IBKR's API will accept."""
    try:
        q = float(qty)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(q) or q <= 0:
        return False
    return abs(q - round(q)) < _WHOLE_SHARE_EPS


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
        # IBKR Error 10243: fractional lots cannot be placed via the API at all.
        # Fail closed here so Flatten/manual place never look like a silent cancel.
        if not is_whole_share_qty(qty):
            return False, IBKR_FRACTIONAL_ORDER_API_MSG, "QTY_FRACTIONAL_API"
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

    summary: dict | None = None
    summary_error: IbkrAccountError | None = None
    try:
        summary = _account.get_account_summary()
    except IbkrAccountError as exc:
        summary_error = exc

    if cmd.operation in ("place", "bracket") and cmd.source not in ("flatten", "kill"):
        if cmd.operation == "place" and (cmd.side or "").upper() == "BUY":
            est = _estimate_notional(cmd)
            if summary_error is not None and est is not None:
                logger.error(
                    "validate: account summary failed — refusing priced BUY: %s",
                    summary_error,
                )
                return (
                    False,
                    f"BuyingPower unavailable — refuse spend: {summary_error}",
                    "BUYING_POWER_UNKNOWN",
                )
            # Prefer live summary when present; if the cache is empty/pending,
            # fail closed only for priced BUY notions (MKT cannot estimate).
            bp = (
                summary.get("BuyingPower")
                if summary is not None and summary.get("connected")
                else None
            )
            if bp is None and summary is not None and summary.get("pending") and est is not None:
                return False, "BuyingPower not yet available — refuse spend", "BUYING_POWER_UNKNOWN"
            if bp is not None and est is not None and est > float(bp):
                return False, f"estimated notional {est:.2f} exceeds BuyingPower {bp}", "BUYING_POWER"

        if cmd.operation == "place" and (cmd.side or "").upper() == "SELL":
            # Position-reducing sells (flatten/close) are allowed; opening a short is not.
            # source=flatten skips anti-short here — reconcile uses long_qty separately.
            if cmd.source not in ("flatten",):
                try:
                    pos_qty = _position_qty(cmd.normalized_symbol() or "")
                except IbkrAccountError as exc:
                    logger.error(
                        "validate: long_qty failed — refusing SELL for %s: %s",
                        cmd.normalized_symbol(),
                        exc,
                    )
                    return (
                        False,
                        f"SELL refused — position unavailable: {exc}",
                        "POSITION_UNAVAILABLE",
                    )
                sell_qty = float(cmd.qty or 0)
                if pos_qty <= 0:
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


def _position_qty(symbol: str) -> float:
    """Verified long qty for ``symbol`` via ``account.long_qty`` (positions SSOT).

    Returns ``0.0`` when flat. Raises ``IbkrAccountError`` when the broker
    position cache cannot be read (caller maps that to ``POSITION_UNAVAILABLE``).
    """
    return _account.long_qty(symbol)
