"""Pre-broker validation for the centralized execution path."""
from __future__ import annotations

import logging
import math
from typing import get_args

from constants import IBKR_FRACTIONAL_ORDER_API_MSG
from execution import inflight as _inflight
from execution.models import ExecutionCommand, Source
from ibkr import account as _account
from ibkr import client as _client
from ibkr import safety as _safety
from ibkr.errors import IbkrAccountError
from ibkr.order_build import PLACEABLE_ORDER_TYPES, normalize_order_type, tif_error

_KNOWN_SOURCES: frozenset[str] = frozenset(get_args(Source))

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
        from sim.mode import is_sim_mode

        if is_sim_mode():
            return True, "OK", None
        ok, reason = _safety.assert_cancel_allowed(
            client_enabled=_client.is_enabled(),
            connected=_client.is_connected(),
        )
        if not ok:
            return False, reason, "CANCEL_GATE"
        return True, "OK", None

    # Everything below can spend. A source outside ADR 007's list -- `auto_live`
    # above all -- is refused outright rather than treated as an ordinary
    # non-protective caller. Cancel stays above: it must never be blocked.
    if cmd.source not in _KNOWN_SOURCES:
        return False, f"unknown order source: {cmd.source}", "SOURCE_INVALID"

    # ADR 018: everything past the cancel branch can increase exposure, so the
    # arm latch is checked here rather than per-operation. A price-only
    # `replace` counts: repricing a resting BUY limit up through the market
    # makes it immediately marketable, which opens a position just as surely as
    # a fresh place. Cancel is above this line because it is protective by
    # definition; other protective sources are exempted inside assert_armed_for.
    armed_ok, armed_reason = _safety.assert_armed_for(cmd.source)
    if not armed_ok:
        return False, armed_reason, "DISARMED"

    if cmd.operation == "replace":
        if cmd.order_id is None:
            return False, "order_id required for replace", "ORDER_ID_MISSING"
        if cmd.limit_price is None and cmd.stop_price is None:
            return False, "replace requires limit_price or stop_price", "REPLACE_PRICE_MISSING"
        if cmd.side is not None or cmd.qty is not None or cmd.symbol is not None:
            # Callers must not attempt to mutate immutable fields via replace.
            pass
        from sim.mode import is_sim_mode

        if is_sim_mode():
            return True, "OK", None
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
        typ = normalize_order_type(cmd.order_type)
        if typ not in PLACEABLE_ORDER_TYPES:
            return False, "order_type must be MKT, LMT, STP, STP LMT, or TRAIL", "ORDER_TYPE_INVALID"
        if typ in ("LMT", "STP LMT") and (cmd.limit_price is None or cmd.limit_price <= 0):
            return False, f"limit_price required for {typ}", "LIMIT_MISSING"
        if typ in ("STP", "STP LMT") and (cmd.stop_price is None or cmd.stop_price <= 0):
            return False, f"stop_price required for {typ}", "STOP_MISSING"
        if typ == "TRAIL" and (cmd.stop_price is None or cmd.stop_price <= 0):
            return False, "stop_price required for TRAIL (trail $)", "TRAIL_MISSING"
    elif cmd.operation == "bracket":
        if cmd.entry_price is None or cmd.stop_price is None or cmd.target_price is None:
            return False, "bracket requires entry/stop/target", "BRACKET_FIELDS"
        shares = int(cmd.shares or cmd.qty or 0)
        if shares <= 0:
            return False, "bracket qty/shares must be > 0", "QTY_INVALID"
        refusal = _bracket_refusal(cmd)
        if refusal is not None:
            return False, refusal[0], refusal[1]
    else:
        return False, f"unknown operation: {cmd.operation}", "OP_INVALID"

    # #91: place and every bracket leg carry the command's TIF.
    bad_tif = tif_error(cmd.tif)
    if bad_tif:
        return False, bad_tif, "TIF_INVALID"

    from sim.mode import is_sim_mode

    # The arm latch was checked above the operation branches, before Sim is
    # consulted: being in Sim decides *where* an allowed order is routed, never
    # *whether* one is allowed (ADR 018).
    if is_sim_mode():
        # Protective sources skip admission so a practice position can always
        # be closed; the sim ledger bounds them to closing a held position.
        if cmd.operation in ("place", "bracket") and cmd.source not in _safety.PROTECTIVE_SOURCES:
            from sim.practice import admission

            ok, reason, code = admission(symbol or "")
            if not ok:
                return False, reason, code
        return True, "OK", None
    ok, reason = _safety.assert_orders_allowed(
        client_enabled=_client.is_enabled(),
        connected=_client.is_connected(),
        account_mode=_client.account_mode(),
        broker_account_kind=_client.broker_account_kind(),
    )
    if not ok:
        return False, reason, "ORDERS_GATE"
    return True, "OK", None


def _bracket_refusal(cmd: ExecutionCommand) -> tuple[str, str] | None:
    """(detail, reason_code) when a bracket's fields do not hang together (#91).

    The broker leg picks its entry side from ``short_entry`` alone, so a
    ``side`` that disagrees would send the opposite trade. Leg prices on the
    wrong side of the entry would fill the stop the moment the entry fills.
    """
    if cmd.source in _safety.PROTECTIVE_SOURCES:
        return (
            f"source {cmd.source} cannot send a bracket -- protective orders carry no legs",
            "BRACKET_SOURCE",
        )
    short = bool(cmd.short_entry)
    entry_side = "SELL" if short else "BUY"
    if cmd.side is not None and str(cmd.side).upper() != entry_side:
        return (
            f"bracket side {cmd.side} disagrees with short_entry={short} "
            f"(entry side is {entry_side})",
            "BRACKET_SIDE",
        )
    if cmd.qty is not None and not is_whole_share_qty(cmd.qty):
        return IBKR_FRACTIONAL_ORDER_API_MSG, "QTY_FRACTIONAL_API"
    try:
        entry = float(cmd.entry_price)  # type: ignore[arg-type]
        stop = float(cmd.stop_price)  # type: ignore[arg-type]
        target = float(cmd.target_price)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "bracket prices must be numbers", "BRACKET_FIELDS"
    if not all(math.isfinite(p) and p > 0 for p in (entry, stop, target)):
        return "bracket prices must be greater than zero", "BRACKET_FIELDS"
    if cmd.limit_price is not None and abs(float(cmd.limit_price) - entry) > 1e-9:
        return "bracket limit_price must equal entry_price", "BRACKET_FIELDS"
    in_order = target < entry < stop if short else stop < entry < target
    if not in_order:
        need = "target < entry < stop" if short else "stop < entry < target"
        return (
            f"{'short' if short else 'long'} bracket needs {need} "
            f"(entry {entry}, stop {stop}, target {target})",
            "BRACKET_GEOMETRY",
        )
    return None


def check_account_and_position(cmd: ExecutionCommand) -> tuple[bool, str, str | None]:
    """Cached account/position checks. Fail closed when data is incomplete for spends."""
    if cmd.operation in ("cancel",):
        return True, "OK", None

    from sim.mode import desk_connected

    if not desk_connected():
        return False, "account checks require IBKR connection", "ACCOUNT_UNAVAILABLE"

    summary: dict | None = None
    summary_error: IbkrAccountError | None = None
    try:
        summary = _account.get_account_summary()
    except IbkrAccountError as exc:
        summary_error = exc

    if cmd.operation in ("place", "bracket") and cmd.source not in ("flatten", "kill"):
        if cmd.operation == "bracket" and getattr(cmd, "short_entry", False):
            return _check_short_entry_sell(cmd)

        # A long bracket is a BUY entry: it gets the same BuyingPower gate a
        # Limit BUY place gets (#91 -- the manual ticket's default legs must
        # not be a way around it).
        long_bracket = cmd.operation == "bracket"
        if long_bracket or (cmd.operation == "place" and (cmd.side or "").upper() == "BUY"):
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

            if long_bracket:
                return _check_long_bracket_not_short(cmd)
            return _check_cover_qty(cmd)

        if cmd.operation == "place" and (cmd.side or "").upper() == "SELL":
            # Position-reducing sells (flatten/close) are allowed; opening a short
            # requires explicit short_entry + IBKR_SHORT_ENABLED + fresh shortable_est
            # (Phase K / ADR 009). source=flatten skips anti-short — reconcile uses
            # long_qty / short cover separately.
            if cmd.source not in ("flatten",):
                if getattr(cmd, "short_entry", False):
                    return _check_short_entry_sell(cmd)
                try:
                    pos_qty = _position_qty(cmd.normalized_symbol() or "")
                except IbkrAccountError as exc:
                    logger.exception(
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
                # Shares already sent and not yet resolved are spent, even
                # though the broker position will not move until they fill.
                working = _inflight.committed_qty(
                    cmd.normalized_symbol() or "", "SELL",
                )
                available = pos_qty - working
                if sell_qty > available + 1e-6:
                    if working > 0:
                        return (
                            False,
                            f"SELL qty {sell_qty} exceeds {available} available "
                            f"(long {pos_qty}, {working} already sent)",
                            "OVERSELL",
                        )
                    return False, f"SELL qty {sell_qty} exceeds position {pos_qty}", "OVERSELL"

    return True, "OK", None


def _check_cover_qty(cmd: ExecutionCommand) -> tuple[bool, str, str | None]:
    """BUY mirror of OVERSELL — never buy past the short being covered.

    Only fires while the account is short that symbol: an opening BUY from
    flat or long is a normal entry and stays on the BuyingPower gate alone.
    """
    symbol = cmd.normalized_symbol() or ""
    try:
        short_open = _account.short_qty(symbol)
    except IbkrAccountError as exc:
        logger.exception(
            "validate: short_qty failed — refusing BUY for %s: %s", symbol, exc,
        )
        return False, f"BUY refused — position unavailable: {exc}", "POSITION_UNAVAILABLE"
    if short_open <= 0:
        return True, "OK", None

    working = _inflight.committed_qty(symbol, "BUY")
    available = short_open - working
    buy_qty = float(cmd.qty or 0)
    if buy_qty > available + 1e-6:
        detail = f"BUY qty {buy_qty} exceeds short position {short_open}"
        if working > 0:
            detail = (
                f"BUY qty {buy_qty} exceeds {available} available "
                f"(short {short_open}, {working} already sent)"
            )
        return False, detail, "OVERCOVER"
    return True, "OK", None


def _check_long_bracket_not_short(cmd: ExecutionCommand) -> tuple[bool, str, str | None]:
    """Refuse a long bracket while short: its SELL legs would re-open the short."""
    symbol = cmd.normalized_symbol() or ""
    try:
        short_open = _account.short_qty(symbol)
    except IbkrAccountError as exc:
        logger.exception(
            "validate: short_qty failed — refusing bracket for %s: %s", symbol, exc,
        )
        return False, f"bracket refused — position unavailable: {exc}", "POSITION_UNAVAILABLE"
    if short_open > 0:
        return (
            False,
            f"bracket refused — account is short {short_open} {symbol}; cover "
            "without legs first (the bracket's exit legs would re-open the short)",
            "BRACKET_WHILE_SHORT",
        )
    return True, "OK", None


def _check_short_entry_sell(cmd: ExecutionCommand) -> tuple[bool, str, str | None]:
    """Short-opening SELL / short bracket path (explicit opt-in only)."""
    from ibkr import safety as _safety
    from ibkr import shortability as _shortability

    if not _safety.short_enabled():
        return False, "IBKR_SHORT_ENABLED is false — short entry locked", "SHORT_DISABLED"
    if cmd.operation == "place" and (cmd.side or "").upper() != "SELL":
        return False, "short_entry requires side=SELL", "SIDE_INVALID"
    snap = _shortability.fetch_shortability(cmd.normalized_symbol() or "")
    ok, detail, code = _shortability.assert_shortable_for_order(snap)
    if not ok:
        return False, detail, code
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
