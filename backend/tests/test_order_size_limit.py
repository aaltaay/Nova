"""Your own order size limit on Paper and Sim (ADR 064): the setting file, the refusals and what never meets it.

Operator decision 2026-10-20: optional, per practice venue, Max shares and Max risk at stop, each off until
typed; a hand order with no stop is refused while Max risk at stop is set. Live keeps its 1-share cap.
"""
from __future__ import annotations

import asyncio
import json

import pytest

import execution.service as exec_svc
import execution.store as store
import execution.telemetry as telemetry
from execution.models import ExecutionCommand, ExecutionReceipt
from execution.size_limit import gate, settings


def _bracket(qty: float = 100, *, entry: float = 10.00, stop: float = 9.80, source: str = "manual",
             side: str = "BUY", key: str = "b", **extra) -> ExecutionCommand:
    target = entry + 0.5 if side == "BUY" else entry - 0.5
    return ExecutionCommand(operation="bracket", idempotency_key=key, source=source,  # type: ignore[arg-type]
                            symbol="AAPL", side=side, qty=qty, order_type="LMT", limit_price=entry,
                            entry_price=entry, stop_price=stop, target_price=target, skip_risk=True, **extra)


def _place(qty: float = 100, *, source: str = "manual", side: str = "BUY", operation: str = "place",
           key: str = "p", **extra) -> ExecutionCommand:
    return ExecutionCommand(operation=operation, idempotency_key=key, source=source,  # type: ignore[arg-type]
                            symbol="AAPL", side=side, qty=qty, order_type="LMT", limit_price=10.00,
                            skip_risk=True, **extra)


def _limit(venue: str = "paper", *, shares: int | None = None, risk: int | None = None) -> None:
    settings.update({venue: {"max_shares": shares, "max_risk_usd": risk}})


# -- the setting file ------------------------------------------------------------------------------
def test_no_file_means_every_limit_is_off():
    now = settings.current()
    assert now["source"] == "default" and now["error"] is None
    assert now["venues"] == {"paper": {"max_shares": None, "max_risk_usd": None},
                             "sim": {"max_shares": None, "max_risk_usd": None}}
    assert gate.refusal(_place(1_000_000), "paper", covers=False) is None


def test_a_save_writes_the_whole_file_and_reads_back():
    before, after = settings.update({"paper": {"max_shares": 100, "max_risk_usd": 20}}, now=1_790_000_000.0)
    assert before["source"] == "default" and after["source"] == "operator"
    doc = json.loads(settings.path().read_text(encoding="utf-8"))
    assert doc == {"schema_version": 1, "set_at": 1_790_000_000.0,
                   "venues": {"paper": {"max_shares": 100, "max_risk_usd": 20},
                              "sim": {"max_shares": None, "max_risk_usd": None}}}
    settings.update({"sim": {"max_risk_usd": 50}})
    settings.reset_for_tests()                                   # a restart reads the file again
    venues = settings.current()["venues"]
    assert venues["paper"] == {"max_shares": 100, "max_risk_usd": 20}
    assert venues["sim"] == {"max_shares": None, "max_risk_usd": 50}
    settings.update({"paper": {"max_shares": None}})              # an empty box clears that limit alone
    assert settings.current()["venues"]["paper"] == {"max_shares": None, "max_risk_usd": 20}


def test_two_saves_at_once_both_land(monkeypatch):
    """Review on PR #1127: each save reads, changes and writes the whole file, so two at once (two Settings
    windows) must not both start from the same old setting and drop one change."""
    import threading
    import time as _time

    from capture import manifest_io

    real_write = manifest_io.write_json_atomic

    def slow_write(path, payload):
        _time.sleep(0.05)                                      # widen the window a race would need
        real_write(path, payload)

    monkeypatch.setattr(manifest_io, "write_json_atomic", slow_write)
    patches = [{"paper": {"max_shares": 100}}, {"sim": {"max_risk_usd": 50}}, {"paper": {"max_risk_usd": 30}}]
    threads = [threading.Thread(target=settings.update, args=(patch,)) for patch in patches]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    want = {"paper": {"max_shares": 100, "max_risk_usd": 30}, "sim": {"max_shares": None, "max_risk_usd": 50}}
    assert settings.current()["venues"] == want
    assert json.loads(settings.path().read_text(encoding="utf-8"))["venues"] == want


@pytest.mark.parametrize("patch, words", [
    ({"paper": {"max_shares": 0}}, "Max shares is 1 to 1,000,000"),
    ({"paper": {"max_shares": 1.5}}, "Max shares is whole shares"),
    ({"paper": {"max_shares": True}}, "Max shares is whole shares"),
    ({"paper": {"max_shares": "100"}}, "Max shares is whole shares"),
    ({"sim": {"max_risk_usd": 0}}, "Max risk at stop is $1 to $1,000,000"),
    ({"sim": {"max_risk_usd": 20.5}}, "Max risk at stop is whole dollars"),
    ({"live": {"max_shares": 10}}, "the order size limit is for Paper and Sim"),
    ({"paper": {"max_qty": 10}}, "Unknown setting max_qty"),
    ({"paper": {}}, "Send paper as"),
    ({}, "Send {paper?"),
])
def test_a_value_out_of_its_rule_is_refused_and_nothing_changes(patch, words):
    _limit(shares=100)
    with pytest.raises(settings.Invalid, match=None) as caught:
        settings.update(patch)
    assert words in str(caught.value)
    assert settings.current()["venues"]["paper"]["max_shares"] == 100


@pytest.mark.parametrize("text", [
    "{not json",
    json.dumps({"schema_version": 2, "venues": {}}),
    json.dumps({"schema_version": 1, "venues": {"paper": {"max_shares": -5, "max_risk_usd": None}}}),
    json.dumps({"schema_version": 1, "venues": "paper"}),
])
def test_a_file_nova_cannot_use_refuses_new_hand_orders_until_saved_again(text):
    """Never read as "no limit": a limit that silently vanished would be the one the operator trusted."""
    settings.path().parent.mkdir(parents=True, exist_ok=True)
    settings.path().write_text(text, encoding="utf-8")
    settings.reset_for_tests()
    now = settings.current()
    assert now["source"] == "unreadable" and now["error"]
    refused = gate.refusal(_place(1), "paper", covers=False)
    assert refused["code"] == "ORDER_SIZE_LIMIT_UNREADABLE"
    assert "saved again in Settings > Loss limits" in refused["text"] and "Flatten and KILL still work" in refused["text"]
    assert gate.refusal(_place(1, side="SELL"), "paper", covers=False) is None      # a close still works
    assert gate.refusal(_place(1, source="bot"), "paper", covers=False) is None     # the bots keep their caps
    assert gate.refusal(_place(1), "live", covers=False) is None                     # Live has its own cap
    settings.update({"paper": {"max_shares": 100}})               # any save writes a fresh file
    assert settings.current()["source"] == "operator"
    assert settings.current()["venues"]["sim"] == {"max_shares": None, "max_risk_usd": None}
    assert gate.refusal(_place(1), "paper", covers=False) is None


# -- the refusals ----------------------------------------------------------------------------------
def test_max_shares_refuses_an_order_over_it_in_its_words():
    _limit(shares=100)
    assert gate.refusal(_place(100), "paper", covers=False) is None
    refused = gate.refusal(_place(250), "paper", covers=False)
    assert refused["code"] == "ORDER_SIZE_LIMIT_SHARES"
    assert refused["text"].startswith("Paper allows at most 100 shares per order; this order is 250 shares.")
    assert "change Max shares in Settings > Loss limits" in refused["text"]
    assert gate.refusal(_place(250), "sim", covers=False) is None                    # Sim has its own numbers


def test_max_risk_at_stop_reads_shares_times_the_distance_to_the_stop():
    _limit("sim", risk=20)
    assert gate.refusal(_bracket(100, entry=10.00, stop=9.80), "sim", covers=False) is None   # exactly $20
    refused = gate.refusal(_bracket(101, entry=10.00, stop=9.80), "sim", covers=False)
    assert refused["code"] == "ORDER_SIZE_LIMIT_RISK"
    assert refused["text"].startswith("Sim allows at most $20 at risk per order; this order risks $20.20 "
                                      "(101 shares x $0.20 from the entry 10.00 to the stop 9.80).")
    sub_dollar = gate.refusal(_bracket(5000, entry=0.5123, stop=0.5080), "sim", covers=False)
    assert "$21.50 (5,000 shares x $0.0043 from the entry 0.5123 to the stop 0.508" in sub_dollar["text"]


def test_a_short_entrys_risk_is_to_its_buy_stop_over_the_entry():
    _limit(shares=500, risk=20)
    short = _bracket(200, entry=9.98, stop=10.11, side="SELL", short_entry=True)
    refused = gate.refusal(short, "paper", covers=False)
    assert refused["code"] == "ORDER_SIZE_LIMIT_RISK" and "this order risks $26" in refused["text"]
    over = gate.refusal(_place(600, side="SELL", short_entry=True), "paper", covers=False)
    assert over["code"] == "ORDER_SIZE_LIMIT_SHARES"


def test_an_order_with_no_stop_is_refused_while_max_risk_at_stop_is_set():
    _limit(risk=20)
    refused = gate.refusal(_place(1), "paper", covers=False)
    assert refused["code"] == "ORDER_SIZE_LIMIT_NO_STOP"
    assert refused["text"].startswith("Paper allows at most $20 at risk per order, and this order has no stop, "
                                      "so its risk is unknown. Attach a stop, or clear Max risk at stop")
    # A stop order's own trigger is not a protective stop.
    stop_buy = ExecutionCommand(operation="place", idempotency_key="s", source="manual", symbol="AAPL", side="BUY",
                                qty=1, order_type="STP", stop_price=10.10, skip_risk=True)
    assert gate.refusal(stop_buy, "paper", covers=False)["code"] == "ORDER_SIZE_LIMIT_NO_STOP"
    _limit(risk=None, shares=10)
    assert gate.refusal(_place(1), "paper", covers=False) is None                     # Max shares alone needs no stop


@pytest.mark.parametrize("cmd, covers", [
    (_place(10_000, side="SELL"), False),                                    # selling what you hold
    (_place(10_000), True),                                                  # a BUY that covers a short
    (_place(10_000, source="flatten", intent="flatten"), False),             # Flatten
    (_place(10_000, source="kill"), False),                                  # KILL
    (_place(10_000, source="cancel_working"), False),
    (_place(10_000, source="bot"), False),                                   # the bots keep their sleeve caps
    (_place(10_000, source="benchmark"), False),
    (_bracket(10_000, source="bot"), False),
    (_place(10_000, operation="cancel"), False),
    (_place(10_000, operation="replace"), False),                            # a stop moved later is never refused
    (_place(10_000, operation="exit_oco", side="SELL"), False),              # an exit pair closes
])
def test_closes_protective_orders_and_the_bots_never_meet_it(cmd, covers):
    _limit(shares=1, risk=1)
    _limit("sim", shares=1, risk=1)
    assert gate.refusal(cmd, "paper", covers=covers) is None
    assert gate.refusal(cmd, "sim", covers=covers) is None


def test_live_never_meets_it():
    _limit(shares=1, risk=1)
    _limit("sim", shares=1, risk=1)
    assert gate.refusal(_place(10_000), "live", covers=False) is None
    assert gate.refusal(_place(10_000), None, covers=False) is None
    assert gate.check("live", 10_000, None, None) is None


# -- at the execution door -------------------------------------------------------------------------
@pytest.fixture
def door(monkeypatch):
    """The real door with the send, the order checks and the account checks stubbed: what it sent, per venue."""
    from sim.mode import reset_for_tests as reset_venue

    store.init_db()
    telemetry.reset_for_tests()
    reset_venue()
    monkeypatch.setattr("bot.venue_levels.venue_changed", lambda old, new: None)
    sent: list[tuple[str, float | None]] = []

    async def record(cmd, execution_id, timings, *, wait_ack=True, reject, venue=None):
        sent.append((venue, cmd.qty))
        return ExecutionReceipt(ok=True, execution_id=execution_id, operation=cmd.operation, source=cmd.source,
                                idempotency_key=cmd.idempotency_key, order_id=1, mode=venue, timings=timings)

    monkeypatch.setattr(exec_svc, "send_broker", record)
    monkeypatch.setattr("execution.validate.validate_command", lambda cmd, venue=None: (True, "OK", None))
    monkeypatch.setattr("execution.validate.check_account_and_position", lambda cmd, **_kw: (True, "OK", None))
    monkeypatch.setattr("execution.validate.covers_short", lambda cmd: False)
    yield sent
    reset_venue()


def _run(cmd: ExecutionCommand):
    return asyncio.run(exec_svc.execute(cmd, wait_ack=False))


@pytest.mark.parametrize("venue", ["paper", "sim"])
def test_the_door_refuses_your_oversized_order_and_sends_nothing(door, venue):
    from sim.mode import set_venue

    set_venue(venue, persist=False)
    _limit(venue, shares=100, risk=20)
    big = _run(_place(250, key=f"{venue}-big"))
    assert big.ok is False and big.reason_code == "ORDER_SIZE_LIMIT_SHARES"
    assert big.error.startswith(f"{venue.title()} allows at most 100 shares per order")
    risky = _run(_bracket(100, entry=10.00, stop=9.70, key=f"{venue}-risky"))
    assert risky.ok is False and risky.reason_code == "ORDER_SIZE_LIMIT_RISK" and "risks $30" in risky.error
    bare = _run(_place(10, key=f"{venue}-bare"))
    assert bare.ok is False and bare.reason_code == "ORDER_SIZE_LIMIT_NO_STOP"
    assert door == []
    ok = _run(_bracket(100, entry=10.00, stop=9.80, key=f"{venue}-ok"))
    assert ok.ok is True and door == [(venue, 100)]


def test_the_door_never_limits_a_close_a_cover_flatten_or_a_bot(door, monkeypatch):
    from sim.mode import set_venue

    set_venue("paper", persist=False)
    _limit(shares=1, risk=1)
    assert _run(_place(500, side="SELL", key="sell")).ok is True                       # selling what you hold
    assert _run(_place(500, source="flatten", intent="flatten", side="SELL", key="flat")).ok is True
    assert _run(_place(500, source="bot", key="bot")).ok is True
    monkeypatch.setattr("execution.validate.covers_short", lambda cmd: True)
    assert _run(_place(500, key="cover")).ok is True                                  # a BUY that covers a short
    assert [venue for venue, _qty in door] == ["paper"] * 4


def test_the_door_leaves_live_to_its_own_cap(door, monkeypatch):
    from sim.mode import set_venue

    monkeypatch.setattr("ibkr.client.is_connected", lambda: True)
    set_venue("live", persist=False)
    _limit(shares=1, risk=1)
    _limit("sim", shares=1, risk=1)
    live = _run(_place(5, key="live"))
    assert live.reason_code is None or not live.reason_code.startswith("ORDER_SIZE_LIMIT")
    assert door and door[0][0] == "live" and door[0][1] == 1.0                       # IBKR_QTY_CAP cut it to 1


# -- the wire ----------------------------------------------------------------------------------------
@pytest.fixture
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from execution.size_limit.routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_get_and_put(client):
    got = client.get("/api/order-size-limit").json()
    assert got["schema_version"] == 1 and got["settings"]["source"] == "default"
    assert got["settings"]["venues"]["paper"] == {"max_shares": None, "max_risk_usd": None}
    assert got["rules"] == {"venues": ["paper", "sim"], "min_shares": 1, "max_shares": 1_000_000,
                            "min_risk_usd": 1, "max_risk_usd": 1_000_000}
    bad = client.put("/api/order-size-limit", json={"paper": {"max_shares": 0}})
    assert bad.status_code == 400 and bad.headers["X-Nova-Reason"] == "ORDER_SIZE_LIMIT_INVALID"
    assert "Max shares is 1 to 1,000,000" in bad.json()["detail"]
    ok = client.put("/api/order-size-limit", json={"paper": {"max_shares": 100, "max_risk_usd": 20}}).json()
    assert ok["settings"]["source"] == "operator"
    assert ok["settings"]["venues"]["paper"] == {"max_shares": 100, "max_risk_usd": 20}
    assert gate.refusal(_place(101), "paper", covers=False)["code"] == "ORDER_SIZE_LIMIT_SHARES"   # at once
    cleared = client.put("/api/order-size-limit", json={"paper": {"max_shares": None, "max_risk_usd": None}}).json()
    assert cleared["settings"]["venues"]["paper"] == {"max_shares": None, "max_risk_usd": None}


def test_a_save_that_cannot_be_written_leaves_the_setting_unchanged(client, monkeypatch):
    _limit(shares=100)

    def fail(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr("capture.manifest_io.write_json_atomic", fail)
    r = client.put("/api/order-size-limit", json={"paper": {"max_shares": 500}})
    assert r.status_code == 503 and "the setting is unchanged" in r.json()["detail"]
    assert settings.current()["venues"]["paper"]["max_shares"] == 100
