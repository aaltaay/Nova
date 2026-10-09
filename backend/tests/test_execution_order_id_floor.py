"""Nova never reuses an IBKR order id after a Gateway restart (check 3; Lean IBKR issue 242).

A Gateway whose settings reset hands a new session a next valid id below ids Nova already sent. ib_async
counts up from it, so without a floor the next order reuses an id that names another ledger row.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import execution.store as store
from diagnostics.collect_order_events import unclaimed_rows
from execution import order_id_floor


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr("paths.cache_dir", lambda: tmp_path)
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    store.init_db()


class _Client:
    """ib_async's Client sequence: ``updateReqId`` only ever raises it."""

    def __init__(self, next_valid_id: int) -> None:
        self.clientId = 17
        self._reqIdSeq = next_valid_id

    def updateReqId(self, min_req_id: int) -> None:
        self._reqIdSeq = max(self._reqIdSeq, min_req_id)

    def getReqId(self) -> int:
        new_id = self._reqIdSeq
        self._reqIdSeq += 1
        return new_id


def _row(key: str, *, venue: str, mode: str, order_id: int, stop_order_id: int | None = None) -> None:
    execution_id, _ = store.reserve(idempotency_key=key, operation="bracket", source="manual", symbol="ZTG",
                                    received_ns=1, payload={"venue": venue})
    store.update_stages(execution_id, status="filled", order_id=order_id, mode=mode, stop_order_id=stop_order_id)


def _session(next_valid_id: int, fills=()) -> SimpleNamespace:
    return SimpleNamespace(client=_Client(next_valid_id), fills=lambda: list(fills))


def test_a_gateway_that_forgot_its_ids_never_gets_one_nova_used_again():
    _row("live-1", venue="live", mode="live", order_id=1000, stop_order_id=1002)
    ib = _session(next_valid_id=1)                       # the Gateway's sequence rolled back
    found = order_id_floor.raise_floor(ib)
    assert found == {"floor": 1002, "before": 1, "after": 1003}
    assert ib.client.getReqId() == 1003


def test_practice_ids_never_set_the_floor_and_a_higher_gateway_id_is_kept():
    _row("paper-1", venue="paper", mode="paper", order_id=90_000)
    _row("sim-1", venue="sim", mode="sim", order_id=80_000)
    _row("live-2", venue="live", mode="live", order_id=500)
    ib = _session(next_valid_id=5_000)
    assert order_id_floor.raise_floor(ib)["after"] == 5_000


def test_executions_this_client_read_back_raise_the_floor_too():
    mine = SimpleNamespace(execution=SimpleNamespace(clientId=17, orderId=7_000))
    other = SimpleNamespace(execution=SimpleNamespace(clientId=0, orderId=9_000_000))
    ib = _session(next_valid_id=10, fills=[mine, other])
    assert order_id_floor.raise_floor(ib)["after"] == 7_001


def test_the_diagnostics_row_fails_on_a_liquidation_and_warns_on_outside_fills():
    loud = unclaimed_rows(status={"counts": {"liquidation": 1}, "events": [{"kind": "liquidation", "ts": 5.0}]},
                          now=10.0)[0]
    assert loud["id"] == "ibkr_unclaimed" and loud["state"] == "fail" and loud["since"] == 5.0
    quiet = unclaimed_rows(status={"counts": {"outside_fill": 2}, "events": []}, now=10.0)[0]
    assert quiet["state"] == "warn" and "2 outside fill" in quiet["detail"]
    assert unclaimed_rows(status={"counts": {}, "events": []}, now=10.0)[0]["state"] == "ok"
