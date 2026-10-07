"""Pre-broker validation for the centralized execution path."""
from __future__ import annotations

import logging
import math
from typing import Any, get_args

from constants import IBKR_FRACTIONAL_ORDER_API_MSG
from execution import flatten_intent as _flatten_intent
from execution import inflight as _inflight  # noqa: F401 -- tests patch committed_qty through it
from execution import position_checks as _positions
from execution.position_checks import covers_short, position_qty as _position_qty  # noqa: F401 -- public names
from execution import session_gate as _session_gate
from execution.models import ExecutionCommand, Source
from execution.venue_door import is_practice as _practice
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


def validate_command(cmd: ExecutionCommand, venue: str | None = None) -> tuple[bool, str, str | None]:
    """Return (ok, detail, reason_code). Pure structural + safety gates.

    ``venue`` is the one the door sends on (``execution.venue_door``); None reads the desk's.
    A kill switch cancel sent to Paper or Sim needs no IBKR connection, whatever the desk shows.
    """
    if not cmd.idempotency_key or not str(cmd.idempotency_key).strip():
        return False, "idempotency_key is required", "IDEMPOTENCY_MISSING"

    if cmd.operation == "cancel":
        if cmd.order_id is None:
            return False, "order_id required for cancel", "ORDER_ID_MISSING"
        if _practice(venue):
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
        if _practice(venue):
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
        # Operator decision 2026-09-21: no exchange takes an unpriced order
        # outside regular hours and IBKR would hold it until the next open, so
        # a MKT is refused on every venue rather than filled (practice) or
        # silently queued (Live). Protective sources are exempt.
        refusal = _session_gate.mkt_outside_rth_refusal(typ, cmd.source)
        if refusal is not None:
            return False, refusal[0], refusal[1]
    elif cmd.operation == "bracket":
        # A short's bracket may leave out its target (ADR 048 1.6) -- on Paper and Sim; Live's
        # two-leg bracket comes with ADR 048's last step, so Live still needs all three.
        optional_target = bool(cmd.short_entry) and _practice(venue)
        if cmd.entry_price is None or cmd.stop_price is None or (cmd.target_price is None and not optional_target):
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

    # The arm latch was checked above the operation branches, before the venue
    # is consulted: being on Paper or Sim decides *where* an allowed order is
    # routed, never *whether* one is allowed (ADR 018). The IBKR env gates
    # below apply to Live only (ADR 020 decision 4).
    if _practice(venue):
        # Admission by the venue's own market (protective sources skip it so a
        # practice position can always be closed) and the no-shorts rule: a
        # SELL is only ever risk-reducing (execution/practice_checks.py).
        from execution.practice_checks import practice_refusal

        refusal = practice_refusal(cmd, venue)
        if refusal is not None:
            return False, refusal[0], refusal[1]
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
        target = float(cmd.target_price) if cmd.target_price is not None else None
    except (TypeError, ValueError):
        return "bracket prices must be numbers", "BRACKET_FIELDS"
    prices = (entry, stop) if target is None else (entry, stop, target)
    if not all(math.isfinite(p) and p > 0 for p in prices):
        return "bracket prices must be greater than zero", "BRACKET_FIELDS"
    if cmd.limit_price is not None and abs(float(cmd.limit_price) - entry) > 1e-9:
        return "bracket limit_price must equal entry_price", "BRACKET_FIELDS"
    if short:
        in_order = entry < stop and (target is None or target < entry)
    else:
        in_order = target is not None and stop < entry < target
    if not in_order:
        need = "target < entry < stop" if short else "stop < entry < target"
        return (
            f"{'short' if short else 'long'} bracket needs {need} "
            f"(entry {entry}, stop {stop}, target {target})",
            "BRACKET_GEOMETRY",
        )
    return None


def check_account_and_position(
    cmd: ExecutionCommand, *, facts: Any = None, borrow: dict | None = None, venue: str | None = None,
) -> tuple[bool, str, str | None]:
    """Cached account/position checks. Fail closed when data is incomplete for spends.

    ``facts`` are the short entry's facts, gathered before the execution lock (``short_sale.prelock``;
    ADR 048 gap 4) -- ``borrow`` a tick-236 read for a caller that has only that; ``venue`` the one
    the door sends on.
    """
    if cmd.operation in ("cancel",):
        return True, "OK", None

    from sim.mode import desk_connected

    # A practice account is a local ledger, readable with the Gateway dark
    # (ADR 020); a protective close on Paper then settles at the last mark.
    # The venue is the one the door sends on: a day cover on Paper while the desk shows Live.
    if not _practice(venue) and not desk_connected():
        return False, "account checks require IBKR connection", "ACCOUNT_UNAVAILABLE"

    if getattr(cmd, "intent", None) == "flatten":
        refused = _flatten_intent.refusal(cmd)  # QA R42: never a second close of the same shares
        if refused:
            return False, refused, _flatten_intent.REASON_CODE

    summary: dict | None = None
    summary_error: IbkrAccountError | None = None
    try:
        summary = _account.get_account_summary()
    except IbkrAccountError as exc:
        summary_error = exc

    if cmd.operation in ("place", "bracket") and cmd.source not in ("flatten", "kill"):
        if getattr(cmd, "short_entry", False):
            # The one short check (ADR 048): the Live key, a limit, no flip, the account, the
            # borrow from the cache, margin and the 25% cushion.
            from short_sale import door as _short_door

            refused = _short_door.refusal(cmd, facts=facts, borrow=borrow, venue=venue)
            return (False, refused[0], refused[1]) if refused else (True, "OK", None)

        # A BUY while the account is short covers it -- a close, like selling what you hold: it is
        # held to the short (OVERCOVER), never to buying power (ADR 048 gap 3).
        # A position Nova cannot read is no cover: the BUY then meets buying power and the position
        # check below, as before.
        if covers_short(cmd):
            return _positions.cover_refusal(cmd)

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
                return _positions.long_bracket_refusal(cmd)
            return _positions.cover_refusal(cmd)

        if cmd.operation == "place" and (cmd.side or "").upper() == "SELL":
            # Position-reducing sells (flatten/close) are allowed; opening a short
            # requires explicit short_entry, which the short check above answers
            # (ADR 009, ADR 048). source=flatten skips anti-short — reconcile uses
            # long_qty / short cover separately.
            if cmd.source not in ("flatten",):
                return _positions.sell_refusal(cmd)

    return True, "OK", None


def _estimate_notional(cmd: ExecutionCommand) -> float | None:
    qty = float(cmd.qty or cmd.shares or 0)
    if qty <= 0:
        return None
    px = cmd.limit_price or cmd.entry_price
    if px is None or px <= 0:
        return None  # market — cannot estimate; skip BP numeric compare
    return qty * float(px)
