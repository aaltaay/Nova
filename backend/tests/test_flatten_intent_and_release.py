"""QA R31 / R32 / R33 (2026-09-22): practice commitments, the ticket's Flatten, the partial-close guard."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import execution.inflight as inflight
import execution.service as exec_svc
from routes import trading_execution as route


def _order(**kw) -> route.OrderRequest:
    base = dict(symbol="GRML", side="SELL", qty=2, order_type="MKT")
    base.update(kw)
    return route.OrderRequest(**base)


# ---------------------------------------------------------------- R32: flatten intent
@pytest.mark.parametrize(
    ("positions", "order", "expected"),
    [
        ([{"symbol": "GRML", "qty": 2}], {}, None),
        ([{"symbol": "GRML", "qty": 5}], {"qty": 2}, None),
        ([{"symbol": "GRML", "qty": -3}], {"side": "BUY", "qty": 3}, None),
        ([], {}, "No open GRML position"),
        ([{"symbol": "GRML", "qty": 2}], {"side": "BUY"}, "does not close"),
        ([{"symbol": "GRML", "qty": 1}], {"qty": 2}, "exceeds"),
        ([{"symbol": "GRML", "qty": 2}], {"short_entry": True}, "cannot open"),
    ],
)
def test_a_flatten_intent_must_close_the_held_position(monkeypatch, positions, order, expected):
    from execution import flatten_intent

    monkeypatch.setattr("ibkr.account.get_positions", lambda: positions)
    monkeypatch.setattr("ibkr.orders.open_orders", lambda: [])
    cmd = route._manual_order_command(_order(intent="flatten", **order), "k", None, 0)
    refusal = flatten_intent.refusal(cmd)  # the door owns the check since QA R42
    if expected is None:
        assert refusal is None
    else:
        assert refusal is not None and expected in refusal


def test_the_flatten_intent_is_sent_as_the_protective_flatten_source():
    flatten = route._manual_order_command(_order(intent="flatten"), "k1", None, 0)
    manual = route._manual_order_command(_order(), "k2", None, 0)
    assert flatten.source == "flatten"
    assert manual.source == "manual"


def test_the_route_hands_the_flatten_to_the_door_with_its_intent(monkeypatch):
    """QA R42: the check runs in the execution door, inside the lock -- the route only passes it on."""
    sent: list = []

    async def fake_execute(cmd, **_kw):
        sent.append(cmd)
        return SimpleNamespace(
            execution_id="e1", duplicate=False,
            legacy_place_dict=lambda: {"ok": False, "reason_code": "FLATTEN_NOT_A_CLOSE"},
        )

    monkeypatch.setattr(route._execution_service, "execute", fake_execute)
    monkeypatch.setattr(route._execution_service, "finalize_http_response", lambda *a, **k: {})
    request = SimpleNamespace(headers={}, state=SimpleNamespace())
    monkeypatch.setattr(route, "ingress_stamps", lambda _req: (0, 0))
    out = asyncio.run(route.place_order(_order(intent="flatten"), request))
    assert out["reason_code"] == "FLATTEN_NOT_A_CLOSE"
    assert [(cmd.source, cmd.intent) for cmd in sent] == [("flatten", "flatten")]


# ---------------------------------------------------------------- R31: fill inside the send
def test_an_order_filled_inside_the_send_frees_its_commitment(monkeypatch):
    """KILL / flatten / bot sends skip the ack wait; a practice fill inside the
    send used to leave the shares "already sent" until a restart."""
    monkeypatch.setattr(exec_svc, "validate", lambda *a, **k: None, raising=False)
    committed: dict = {}

    def fake_commit(cmd, execution_id, symbol):
        inflight.commit(execution_id, symbol=symbol, side=cmd.side, qty=cmd.qty)
        committed["id"] = execution_id

    async def fake_send(cmd, execution_id, timings, wait_ack=False, reject=None):
        timings.filled_ns = 1
        return SimpleNamespace(ok=True, order_id=77, broker_status="Filled", timings=timings)

    monkeypatch.setattr(exec_svc, "_commit_position", fake_commit)
    monkeypatch.setattr(exec_svc, "send_broker", fake_send)

    # Drive only the tail of execute(): commit, send, then the release decision.
    timings = SimpleNamespace(filled_ns=None)
    cmd = SimpleNamespace(side="SELL", qty=2.0)

    async def tail():
        exec_svc._commit_position(cmd, "exec-r31", "GRML")
        receipt = await exec_svc.send_broker(cmd, "exec-r31", timings, wait_ack=False)
        if receipt.ok:
            inflight.attach_order("exec-r31", receipt.order_id)
            if receipt.timings.filled_ns or str(receipt.broker_status or "") == "Filled":
                inflight.release_execution("exec-r31")
        return receipt

    asyncio.run(tail())
    assert committed["id"] == "exec-r31"
    assert all(row.get("execution_id") != "exec-r31" for row in inflight.snapshot())


def test_execute_source_carries_the_release_after_attach():
    """The release sits right after attach_order in execute() itself."""
    import inspect

    source = inspect.getsource(exec_svc.execute)
    attach = source.index("inflight.attach_order(execution_id, receipt.order_id)")
    release = source.index("inflight.release_execution(execution_id)", attach)
    assert "filled_ns" in source[attach:release]


# ---------------------------------------------------------------- R33: sent size from the record
def test_the_partial_close_guard_reads_the_sent_size_from_the_record(monkeypatch):
    from bot import flatten as flatten_mod

    monkeypatch.setattr(
        "execution.store.get_by_id",
        lambda eid: {"payload": {"sent_qty": 1.0}} if eid == "exec-r33" else None,
    )
    receipt = SimpleNamespace(payload={}, execution_id="exec-r33")
    assert flatten_mod._sent_qty(receipt) == 1.0
    assert flatten_mod._short_close({"ok": True, "sent_qty": 1.0}, 2.0) == "flatten sent 1 of 2 shares"
    assert flatten_mod._sent_qty(SimpleNamespace(payload={}, execution_id=None)) is None
