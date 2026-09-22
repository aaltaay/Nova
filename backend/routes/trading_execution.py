"""Thin ADR 007 HTTP execution routes and client timing contract."""
from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from constants_ibkr import IBKR_ORDER_TIF_DEFAULT
from execution import service as _execution_service
from execution import verification_gate
from execution.models import ExecutionCommand
from execution.timing import ingress_stamps
from ibkr import orders as _orders
from ibkr.errors import IbkrAccountError
from ibkr.order_build import normalize_order_type, normalize_tif

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ibkr"])


class BrowserTimingRequest(BaseModel):
    """Paired browser wall/monotonic stamps; no cross-clock subtraction."""

    action_wall_ms: float
    action_performance_ms: float
    request_wall_ms: float
    request_performance_ms: float


class OrderRequest(BaseModel):
    symbol: str
    side: str
    qty: float = Field(gt=0)
    order_type: str = "MKT"
    limit_price: float | None = None
    stop_price: float | None = None
    reference_price: float | None = Field(default=None, gt=0)
    outside_rth: bool = False
    short_entry: bool = False
    # #91: validated by execution.validate (TIF_INVALID), default DAY.
    tif: str = IBKR_ORDER_TIF_DEFAULT
    # #91: the ticket's default protective legs. Both or neither, on a Limit
    # entry only; present -> operation "bracket" through the same execute().
    take_profit_price: float | None = Field(default=None, gt=0)
    stop_loss_price: float | None = Field(default=None, gt=0)
    idempotency_key: str | None = None
    client_timing: BrowserTimingRequest | None = None
    # The ticket's Flatten (QA R32): a close of the held position, sent as a
    # protective ``flatten`` -- never clamped by the one-share test gate. The
    # door refuses it past the shares not already being closed (QA R42).
    intent: Literal["flatten"] | None = None

    @model_validator(mode="after")
    def _legs_ride_a_limit_entry(self) -> "OrderRequest":
        legs = (self.take_profit_price, self.stop_loss_price)
        if all(leg is None for leg in legs):
            return self
        if any(leg is None for leg in legs):
            raise ValueError("take_profit_price and stop_loss_price go together")
        if normalize_order_type(self.order_type) != "LMT" or self.limit_price is None:
            raise ValueError("protective legs attach to a Limit entry only")
        return self


class ReplaceRequest(BaseModel):
    """Price-only replace. Side/symbol/qty are immutable."""

    limit_price: float | None = None
    stop_price: float | None = None
    reference_price: float | None = Field(default=None, gt=0)
    idempotency_key: str | None = None
    client_timing: BrowserTimingRequest | None = None


def _browser_timing(
    request: Request,
    body: BrowserTimingRequest | None = None,
) -> dict | None:
    if body is not None:
        return body.model_dump()
    names = {
        "action_wall_ms": "x-nova-action-wall-ms",
        "action_performance_ms": "x-nova-action-performance-ms",
        "request_wall_ms": "x-nova-request-wall-ms",
        "request_performance_ms": "x-nova-request-performance-ms",
    }
    values = {key: request.headers.get(header) for key, header in names.items()}
    return values if any(value is not None for value in values.values()) else None


def _response(receipt) -> dict:
    result = receipt.legacy_place_dict()
    result["measurement"] = _execution_service.finalize_http_response(
        receipt.execution_id, duplicate=receipt.duplicate,
    )
    return result


def _manual_order_command(
    req: OrderRequest, key: str, client_timing: dict | None, ingress_wall: int,
) -> ExecutionCommand:
    """Ticket request -> ADR 007 command. Legs make it a bracket, same door."""
    common = dict(
        idempotency_key=key,
        source="flatten" if req.intent == "flatten" else "manual",
        # Checked in the door against the position less the closes already
        # working, inside the execution lock (execution.flatten_intent, QA R42).
        intent=req.intent,
        symbol=req.symbol.upper(),
        side=req.side.upper(),
        qty=req.qty,
        reference_price=req.reference_price,
        outside_rth=req.outside_rth,
        short_entry=bool(req.short_entry),
        tif=normalize_tif(req.tif),
        skip_risk=True,
        skip_concurrency=True,
        client_timing=client_timing,
        backend_ingress_wall_ns=ingress_wall,
    )
    if req.take_profit_price is None:
        return ExecutionCommand(
            operation="place",
            order_type=normalize_order_type(req.order_type),
            limit_price=req.limit_price,
            stop_price=req.stop_price,
            **common,
        )
    return ExecutionCommand(
        operation="bracket",
        order_type="LMT",
        limit_price=req.limit_price,
        entry_price=req.limit_price,
        target_price=req.take_profit_price,
        stop_price=req.stop_loss_price,
        **common,
    )


@router.post("/order")
async def place_order(req: OrderRequest, request: Request) -> dict:
    ingress_perf, ingress_wall = ingress_stamps(request)
    key = (req.idempotency_key or "").strip() or str(uuid.uuid4())
    receipt = await _execution_service.execute(
        _manual_order_command(
            req, key, _browser_timing(request, req.client_timing), ingress_wall,
        ),
        received_ns=ingress_perf,
    )
    return _response(receipt)


@router.post("/verification/{symbol}/acknowledge")
async def acknowledge_verification(symbol: str) -> dict:
    normalized = symbol.strip().upper()
    if not normalized:
        raise HTTPException(status_code=400, detail="symbol is required")
    return {
        "ok": True,
        "symbol": normalized,
        "cleared": verification_gate.acknowledge(normalized),
    }


@router.delete("/order/{order_id}")
async def cancel_order(
    order_id: int,
    request: Request,
    idempotency_key: str | None = None,
) -> dict:
    ingress_perf, ingress_wall = ingress_stamps(request)
    key = (idempotency_key or "").strip() or f"cancel:{order_id}:{uuid.uuid4()}"
    receipt = await _execution_service.execute(
        ExecutionCommand(
            operation="cancel",
            idempotency_key=key,
            source="manual",
            order_id=order_id,
            skip_risk=True,
            skip_concurrency=True,
            client_timing=_browser_timing(request),
            backend_ingress_wall_ns=ingress_wall,
        ),
        received_ns=ingress_perf,
    )
    result = _response(receipt)
    return {
        key: result.get(key)
        for key in (
            "ok", "error", "execution_id", "timings", "broker_status",
            "duplicate", "measurement",
        )
    }


@router.delete("/orders")
async def cancel_orders_for_symbol(
    request: Request,
    symbol: str | None = None,
    all_symbols: bool = False,
) -> dict:
    """Cancel working orders via per-order ADR 007 cancels (no SDK bypass).

    - ``symbol=XYZ``: cancel that symbol only (legacy).
    - ``all_symbols=true``: cancel every open order on the connected account.
    """
    sym = (symbol or "").strip().upper()
    if not all_symbols and not sym:
        return {
            "ok": False, "error": "symbol is required (or pass all_symbols=true)",
            "cancelled": [], "failed": [],
        }
    try:
        open_list = _orders.open_orders()
    except IbkrAccountError as exc:
        return {
            "ok": False, "error": str(exc), "cancelled": [], "failed": [],
        }
    ingress_perf, ingress_wall = ingress_stamps(request)
    browser = _browser_timing(request)
    cancelled: list[int] = []
    failed: list[dict] = []
    scope_key = "ALL" if all_symbols else sym
    for row in open_list:
        row_sym = str(row.get("symbol", "")).upper()
        if row.get("order_id") is None:
            continue
        if not all_symbols and row_sym != sym:
            continue
        oid = int(row["order_id"])
        receipt = await _execution_service.execute(
            ExecutionCommand(
                operation="cancel",
                idempotency_key=f"cancel-all:{scope_key}:{oid}:{uuid.uuid4()}",
                source="manual",
                symbol=row_sym or None,
                order_id=oid,
                skip_risk=True,
                skip_concurrency=True,
                client_timing=browser,
                backend_ingress_wall_ns=ingress_wall,
            ),
            received_ns=ingress_perf,
        )
        _execution_service.finalize_http_response(
            receipt.execution_id, duplicate=receipt.duplicate,
        )
        if receipt.ok:
            cancelled.append(oid)
        else:
            failed.append({"order_id": oid, "error": receipt.error})
    out: dict = {
        "ok": not failed,
        "cancelled": cancelled,
        "failed": failed,
        "error": None if not failed else f"{len(failed)} cancel(s) failed",
    }
    if not all_symbols:
        out["symbol"] = sym
    else:
        out["all_symbols"] = True
    return out


@router.post("/flatten-account")
async def flatten_account_route() -> dict:
    """Whole-account MKT flatten -- same door bot breakers already use.

    Calls ``bot.flatten.flatten_account_with_retry`` (execution source=flatten).
    Not a second place / cancel stack.
    """
    from bot.flatten import flatten_account_with_retry

    return await flatten_account_with_retry()


@router.patch("/order/{order_id}")
async def replace_order(
    order_id: int,
    req: ReplaceRequest,
    request: Request,
) -> dict:
    ingress_perf, ingress_wall = ingress_stamps(request)
    key = (req.idempotency_key or "").strip() or f"replace:{order_id}:{uuid.uuid4()}"
    receipt = await _execution_service.execute(
        ExecutionCommand(
            operation="replace",
            idempotency_key=key,
            source="manual",
            order_id=order_id,
            limit_price=req.limit_price,
            stop_price=req.stop_price,
            reference_price=req.reference_price,
            skip_risk=True,
            skip_concurrency=True,
            client_timing=_browser_timing(request, req.client_timing),
            backend_ingress_wall_ns=ingress_wall,
        ),
        received_ns=ingress_perf,
    )
    return _response(receipt)


@router.get("/executions")
async def list_executions(
    limit: int | None = None,
    symbol: str | None = None,
) -> list[dict]:
    from constants import EXECUTION_ACTIVITY_DEFAULT_LIMIT
    from execution.activity import recent_activity

    cap = EXECUTION_ACTIVITY_DEFAULT_LIMIT if limit is None else limit
    return recent_activity(limit=cap, symbol=symbol)


@router.get("/execution/{execution_id}")
async def get_execution(execution_id: str) -> dict:
    from execution.service import get_execution as _get

    row = _get(execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail="execution not found")
    return row


@router.get("/execution-latency")
async def execution_latency() -> dict:
    from execution.service import latency_summary

    return latency_summary()
