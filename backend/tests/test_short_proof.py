"""The Live short proof (ADR 048 step 6): what Nova saw on Paper before a short may go to Live.

Three Paper days with shorts, each reviewed by the operator, and four drills with a Paper short open.
The proof is recorded as it happens (``short_proof.store``), never complete while no day can be marked
reviewed (#778, question 3), and the door refuses a Live short until it is (``SHORT_PROOF_INCOMPLETE``).
"""
from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from constants_shorts import SHORT_PROOF_DRILLS
from short_proof import evidence, observe, store
from short_proof import view as proof_view


@pytest.fixture(autouse=True)
def fresh_proof(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    store.reset_for_tests()
    observe.reset_for_tests()
    yield tmp_path
    store.reset_for_tests()
    observe.reset_for_tests()


def _row(order_id: int, *, status: str = "Filled", side: str = "SELL", short_entry: bool = False,
         origin: str | None = None, position_side: str | None = None, effect: str | None = None,
         fill_ts: float = 1_791_390_000.0, symbol: str = "FADE", qty: float = 500) -> dict:
    return {"order_id": order_id, "status": status, "side": side, "short_entry": short_entry, "order_origin": origin,
            "position_side": position_side, "effect": effect, "fill_ts": fill_ts if status == "Filled" else None,
            "symbol": symbol, "qty": qty, "filled_qty": qty if status == "Filled" else 0}


class Ledger:
    """The Paper ledger as the observer reads it."""

    def __init__(self, rows=(), held=None, created_ts: float = 1.0) -> None:
        self.rows = list(rows)
        self.held = dict(held or {})
        self.created_ts = created_ts
        self.events = [object()] * len(self.rows)

    def closed_orders(self):
        return [dict(r) for r in reversed(self.rows)]

    def held_symbols(self):
        return sorted(self.held)

    def held_qty(self, symbol):
        return self.held.get(symbol, 0.0)


def _broker(rows=(), held=None, working=()):
    return SimpleNamespace(ledger=Ledger(rows, held), working_orders=lambda: [dict(w) for w in working])


# ── the store ──────────────────────────────────────────────────────────────────

def test_a_new_proof_is_empty_and_incomplete(fresh_proof):
    doc, error = store.read()
    assert error is None and doc["days"] == {} and set(doc["drills"]) == set(SHORT_PROOF_DRILLS)
    complete, missing = proof_view.status()
    assert complete is False
    assert "0 of 3 reviewed Paper days" in missing and "question 3" in missing
    for words in ("Freeze all orders", "Flatten", "15:55 cover", "Gateway drop"):
        assert words in missing


def test_an_unknown_version_or_a_damaged_file_is_never_read_and_never_written_over(fresh_proof):
    path = store.path()
    path.write_text(json.dumps({"schema_version": 9, "days": {}}), encoding="utf-8")
    store.reset_for_tests()
    doc, error = store.read()
    assert doc is None and "schema_version" in error
    assert proof_view.status()[0] is False and "could not be read" in proof_view.status()[1]
    assert store.record_drill("flatten", True, {"at": 1.0, "key": "x"}) is False
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 9      # untouched

    path.write_text("{not json", encoding="utf-8")
    store.reset_for_tests()
    assert store.read()[0] is None and proof_view.status()[0] is False


def test_a_drill_keeps_its_first_pass_and_its_last_misses(fresh_proof):
    assert store.record_drill("freeze", False, {"at": 1.0, "key": "a", "detail": "no stop kept"}) is True
    assert store.record_drill("freeze", False, {"at": 1.0, "key": "a", "detail": "no stop kept"}) is False
    assert store.record_drill("freeze", True, {"at": 2.0, "key": "b", "detail": "kept"}) is True
    assert store.record_drill("freeze", True, {"at": 3.0, "key": "c", "detail": "kept again"}) is False
    store.reset_for_tests()                                     # read back from the file
    drill = store.read()[0]["drills"]["freeze"]
    assert drill["passed"]["key"] == "b" and [r["key"] for r in drill["failed"]] == ["a"]
    with pytest.raises(ValueError):
        store.record_drill("nope", True, {})


# ── what counts ────────────────────────────────────────────────────────────────

def test_a_short_day_is_a_filled_short_entry_on_its_practice_day():
    # 2026-10-08 03:59 ET belongs to 10-07's practice day (it starts at 04:00 ET).
    before_four = 1_791_446_340.0     # 2026-10-08 03:59 ET
    rows = [_row(1, short_entry=True, fill_ts=1_791_390_000.0), _row(2, short_entry=True, fill_ts=before_four),
            _row(3, short_entry=True, status="Cancelled"), _row(4, side="BUY")]
    fills = evidence.short_fills(rows)
    assert [(f["order_id"], f["day"]) for f in fills] == [(1, "2026-10-07"), (2, "2026-10-07")]


def test_only_a_flatten_or_day_cover_that_covered_a_short_counts():
    rows = [
        _row(10, side="BUY", origin="ticket_flatten", position_side="short", effect="closes"),
        _row(11, side="SELL", origin="ticket_flatten", position_side="long", effect="closes"),   # a long's flatten
        _row(12, side="BUY", origin="day_cover", position_side="short", effect="closes"),
        _row(13, side="BUY", origin="day_cover", position_side="short", effect="closes", status="Cancelled"),
        _row(14, side="BUY", origin=None, position_side="short", effect="closes"),                # your own cover
    ]
    assert [c["order_id"] for c in evidence.covers(rows, "ticket_flatten")] == [10]
    assert [c["order_id"] for c in evidence.covers(rows, "day_cover")] == [12]


def test_freeze_passes_only_when_every_short_kept_its_buy_stop():
    kept = [{"order_id": 7, "symbol": "FADE", "side": "BUY", "order_type": "STP", "qty": 500}]
    assert evidence.freeze(5.0, {}, kept) is None                                  # no short open: no drill
    passed, run = evidence.freeze(5.0, {"FADE": 500.0}, kept)
    assert passed is True and "kept its buy stop" in run["detail"]
    passed, run = evidence.freeze(5.0, {"FADE": 500.0, "RDYN": 100.0}, kept)
    assert passed is False and "RDYN" in run["detail"]


# ── the observer ───────────────────────────────────────────────────────────────

def test_the_observer_records_short_days_and_the_flatten_and_day_cover_drills(monkeypatch):
    rows = [_row(1, short_entry=True), _row(2, side="BUY", origin="ticket_flatten", position_side="short",
                                            effect="closes", qty=500)]
    broker = _broker(rows)
    monkeypatch.setattr(observe, "_paper", lambda: broker)
    monkeypatch.setattr(observe, "_session_up", lambda: True)
    observe.pass_once(now=100.0)
    doc = store.read()[0]
    assert doc["days"]["2026-10-07"]["orders"] == [1] and doc["days"]["2026-10-07"]["symbols"] == ["FADE"]
    assert doc["drills"]["flatten"]["passed"]["detail"] == "Flatten covered 500 FADE short on Paper"
    assert doc["drills"]["day_cover"]["passed"] is None

    broker.ledger.rows.append(_row(3, side="BUY", origin="day_cover", position_side="short", effect="closes"))
    broker.ledger.events.append(object())
    observe._state["scanned_at"] = 0.0          # the next scan is due
    observe.pass_once(now=110.0)
    assert store.read()[0]["drills"]["day_cover"]["passed"]["order_id"] == 3


def test_a_gateway_drop_with_a_paper_short_open_is_judged_when_the_session_is_back(monkeypatch):
    up = {"now": True}
    stop = {"order_id": 9, "symbol": "FADE", "side": "BUY", "order_type": "STP"}
    broker = _broker(held={"FADE": -500.0}, working=[stop])
    monkeypatch.setattr(observe, "_paper", lambda: broker)
    monkeypatch.setattr(observe, "_session_up", lambda: up["now"])

    observe.pass_once(now=100.0)                 # the session is up: nothing yet
    up["now"] = False
    observe.pass_once(now=101.0)                 # it dropped with FADE short
    assert store.read()[0]["drills"]["gateway_drop"]["passed"] is None
    up["now"] = True
    observe.pass_once(now=131.0)                 # back: FADE still has its buy stop
    run = store.read()[0]["drills"]["gateway_drop"]["passed"]
    assert run["at"] == 101.0 and run["back_at"] == 131.0 and "30 s" in run["detail"]


def test_a_gateway_drop_that_leaves_a_short_unprotected_does_not_pass(monkeypatch):
    up = {"now": True}
    broker = _broker(held={"FADE": -500.0}, working=[])
    monkeypatch.setattr(observe, "_paper", lambda: broker)
    monkeypatch.setattr(observe, "_session_up", lambda: up["now"])
    observe.pass_once(now=100.0)
    up["now"] = False
    observe.pass_once(now=101.0)
    up["now"] = True
    observe.pass_once(now=105.0)
    drill = store.read()[0]["drills"]["gateway_drop"]
    assert drill["passed"] is None and "FADE had no buy stop working" in drill["failed"][0]["detail"]


def test_a_drop_with_no_paper_short_open_is_no_drill(monkeypatch):
    up = {"now": True}
    monkeypatch.setattr(observe, "_paper", lambda: _broker(held={"FADE": 200.0}))     # long, not short
    monkeypatch.setattr(observe, "_session_up", lambda: up["now"])
    observe.pass_once(now=100.0)
    up["now"] = False
    observe.pass_once(now=101.0)
    up["now"] = True
    observe.pass_once(now=102.0)
    drill = store.read()[0]["drills"]["gateway_drop"]
    assert drill["passed"] is None and drill["failed"] == []


def test_note_freeze_never_raises_and_records_what_the_sweep_kept(monkeypatch):
    monkeypatch.setattr(observe, "_paper", lambda: _broker(held={"FADE": -500.0}))
    sweep = [{"venue": "live", "kept": []},
             {"venue": "paper", "kept": [{"order_id": 7, "symbol": "FADE", "side": "BUY", "order_type": "STP"}]}]
    observe.note_freeze(sweep, now=50.0)
    assert store.read()[0]["drills"]["freeze"]["passed"]["at"] == 50.0
    monkeypatch.setattr(observe, "_paper", lambda: (_ for _ in ()).throw(RuntimeError("ledger gone")))
    observe.note_freeze(sweep, now=60.0)        # logged, never raised: the trip itself stands


# ── complete only with reviewed days ───────────────────────────────────────────

def _all_drills_and_three_days() -> None:
    for day in ("2026-10-08", "2026-10-09", "2026-10-12"):
        store.record_short_fills([{"day": day, "order_id": hash(day) % 1000, "symbol": "FADE", "ts": 1.0}])
    for name in SHORT_PROOF_DRILLS:
        store.record_drill(name, True, {"at": 1.0, "key": name, "detail": "done"})


def test_the_proof_never_completes_while_no_day_can_be_marked_reviewed(fresh_proof):
    _all_drills_and_three_days()
    # A review written into the file by hand counts for nothing while the review is closed (#778, question 3).
    path = store.path()
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["reviews"] = {day: {"ok": True} for day in doc["days"]}
    path.write_text(json.dumps(doc), encoding="utf-8")
    store.reset_for_tests()
    complete, missing = proof_view.status()
    assert complete is False and "0 of 3 reviewed" in missing and "drills" not in missing


def test_three_reviewed_days_and_the_four_drills_complete_it_once_reviews_open(fresh_proof, monkeypatch):
    _all_drills_and_three_days()
    monkeypatch.setattr(proof_view, "SHORT_PROOF_REVIEW_OPEN", True)
    assert proof_view.status()[0] is False                 # three days with shorts, none reviewed
    path = store.path()
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["reviews"] = {day: {"ok": True} for day in doc["days"]}
    path.write_text(json.dumps(doc), encoding="utf-8")
    store.reset_for_tests()
    assert proof_view.status() == (True, "")


# ── the checklist ──────────────────────────────────────────────────────────────

def test_the_checklist_lists_the_operators_steps_in_order(fresh_proof, monkeypatch):
    from ibkr import client as client_mod
    from ibkr import live_book
    from ibkr import safety as safety_mod
    from setup_scanner import short_tests

    monkeypatch.setattr(client_mod, "account_mode", lambda: "live")
    monkeypatch.setattr(live_book, "account_summary",
                        lambda: {"connected": True, "account_class": "margin", "ibkr_account_class": "cash",
                                 "account_class_source": "override", "NetLiquidation": 5_000.0})
    monkeypatch.setattr(short_tests, "test_in_play", lambda setup: {"state": "queued"})
    monkeypatch.setattr(safety_mod, "short_enabled", lambda: False)
    monkeypatch.setattr(observe, "_paper", lambda: _broker())
    store.record_drill("flatten", True, {"at": 7.0, "key": "f", "detail": "Flatten covered 500 FADE short"})

    view = proof_view.view()
    assert [s["id"] for s in view["steps"]] == [
        "margin_account", "practice_reset", "short_tests", "paper_days", "drill_freeze", "drill_flatten",
        "drill_day_cover", "drill_gateway_drop", "live_key"]
    steps = {s["id"]: s for s in view["steps"]}
    assert steps["margin_account"]["ok"] is False and "override" in steps["margin_account"]["text"]
    assert steps["short_tests"]["ok"] is False and steps["short_tests"]["value"] == "0 of 5"
    assert steps["drill_flatten"]["ok"] is True and steps["drill_flatten"]["at"] == 7.0
    assert steps["drill_freeze"]["ok"] is False and steps["drill_freeze"]["how"]
    assert steps["paper_days"]["ok"] is False and "question 3" in steps["paper_days"]["text"]
    assert steps["live_key"]["ok"] is False and steps["live_key"]["enforced"] is True
    assert (view["complete"], view["done"], view["total"]) == (False, 1, 7)
    assert view["review"]["open"] is False


def test_the_margin_step_is_unknown_while_ibkr_cannot_say(fresh_proof, monkeypatch):
    from ibkr import client as client_mod
    from ibkr import live_book
    from ibkr.errors import IbkrAccountError

    monkeypatch.setattr(client_mod, "account_mode", lambda: "disconnected")

    def down():
        raise IbkrAccountError("IBKR transport down -- Gateway not connected")

    monkeypatch.setattr(live_book, "account_summary", down)
    step = proof_view._margin_step()
    assert step["ok"] is None and "Gateway not connected" in step["text"]
    monkeypatch.setattr(live_book, "account_summary",
                        lambda: {"connected": True, "ibkr_account_class": "margin", "NetLiquidation": 5_000.0})
    assert proof_view._margin_step()["ok"] is True


def test_the_route_answers_the_checklist(fresh_proof, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from short_proof.routes import router

    monkeypatch.setattr(proof_view, "view", lambda: {"schema_version": 1, "complete": False, "steps": []})
    app = FastAPI()
    app.include_router(router)
    body = TestClient(app).get("/api/short-proof").json()
    assert body == {"schema_version": 1, "complete": False, "steps": []}


def test_the_store_lives_in_the_operator_cache(fresh_proof):
    assert store.path() == fresh_proof / "short-proof.json"
    store.record_drill("day_cover", True, {"at": time.time(), "key": "d", "detail": "done"})
    assert json.loads(store.path().read_text(encoding="utf-8"))["schema_version"] == 1
