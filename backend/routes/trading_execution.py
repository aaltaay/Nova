"""Thin ADR 007 HTTP execution routes and client timing contract."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from execution import service as _execution_service
from execution import verification_gate
from execution.models import ExecutionCommand
from execution.timing import ingress_stamps
from ibkr import orders as _orders
from ibkr.errors import IbkrAccountError

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
    idempotency_key: str | None = None
    client_timing: BrowserTimingRequest | None = None


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


@router.post("/order")
async def place_order(req: OrderRequest, request: Request) -> dict:
    ingress_perf, ingress_wall = ingress_stamps(request)
    key = (req.idempotency_key or "").strip() or str(uuid.uuid4())
    receipt = await _execution_service.execute(
        ExecutionCommand(
            operation="place",
            idempotency_key=key,
            source="manual",
            symbol=req.symbol.upper(),
            side=req.side.upper(),
            qty=req.qty,
            order_type=req.order_type.upper(),
            limit_price=req.limit_price,
            stop_price=req.stop_price,
            reference_price=req.reference_price,
            outside_rth=req.outside_rth,
            short_entry=bool(req.short_entry),
            skip_risk=True,
            skip_concurrency=True,
            client_timing=_browser_timing(request, req.client_timing),
            backend_ingress_wall_ns=ingress_wall,
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
