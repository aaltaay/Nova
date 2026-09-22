"""GET /api/practice/history: the practice ledger as history, derived from its events only."""
from __future__ import annotations

import logging
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from practice import broker as practice_broker, history, persist
from practice.broker import PracticeBroker
from practice.clock import ET, iso_et
from practice.fees import for_fill
from practice.ledger import Ledger
from practice.routes import router
from sim.fill_model import Reference

OPENED = datetime(2026, 9, 21, 9, 0, tzinfo=ET).timestamp()
DAY1 = datetime(2026, 9, 21, 10, 0, tzinfo=ET).timestamp()  # Monday
DAY2 = DAY1 + 24 * 3600
ROLLOVER = datetime(2026, 9, 22, 4, 0, tzinfo=ET).timestamp()

SHAPE = {
    "venue", "account_id", "range", "range_start", "schema_version", "starting_cash", "ledger_opened_at",
    "equity", "fills", "by_source", "daily", "archives", "components", "warnings",
}
POINT = {"ts", "net_liquidation", "cash", "realized", "unrealized"}
FILL = {
    "ts", "order_id", "symbol", "side", "qty", "price", "source", "bot_id", "commission", "fees", "realized",
    "fill_estimated", "fill_basis",
}


class Clock:
    """A reference with nothing quoted and a clock the test sets -- history never needs a fill."""

    now = DAY1 + 100

    def reference(self, symbol: str) -> Reference:
        return Reference(None, live=True)

    def admission(self, symbol: str):
        return False, "dark", "PRACTICE_NO_LIVE_PRINT"

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def now_ts(self) -> float:
        return float(Clock.now)


def _row(oid, symbol, side, qty, ts, source, bot_id) -> dict:
    return {
        "order_id": oid, "symbol": symbol, "side": side, "qty": float(qty), "filled_qty": 0.0,
        "remaining_qty": float(qty), "order_type": "MKT", "limit_price": None, "stop_price": None,
        "status": "Submitted", "placed_ts": ts, "source": "nova", "order_source": source, "bot_id": bot_id,
    }


def fill(ledger: Ledger, oid: int, *, ts: float, symbol: str, side: str, qty: float, price: float,
         source: str = "manual", bot_id: str | None = None) -> None:
    ledger.place(_row(oid, symbol, side, qty, ts, source, bot_id), ts=ts, source=source, bot_id=bot_id)
    ledger.fill(oid, ts=ts, price=price, basis="live_quote")


def two_days() -> Ledger:
    ledger = Ledger(100_000, created_ts=OPENED)
    fill(ledger, 1, ts=DAY1, symbol="GRML", side="BUY", qty=100, price=8.80)
    fill(ledger, 2, ts=DAY1 + 60, symbol="GRML", side="SELL", qty=100, price=9.30)
    fill(ledger, 3, ts=DAY2, symbol="QNME", side="BUY", qty=10, price=14.0, source="bot", bot_id="momo-1")
    return ledger


def paper_broker(tmp_path, *, created_ts: float = OPENED) -> PracticeBroker:
    path = str(tmp_path / "practice-paper.json")
    return PracticeBroker(Clock(), Ledger(100_000, created_ts=created_ts), "NOVA-PAPER", venue="paper", persist_path=path)


@pytest.fixture
def client(monkeypatch):
    practice_broker.reset_for_tests()
    monkeypatch.setattr(practice_broker, "LiveReference", Clock)
    Clock.now = DAY1 + 100
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as test_client:
        yield test_client
    practice_broker.reset_for_tests()


# ------------------------------------------------------------------- equity
def test_equity_is_the_net_liquidation_after_each_fill_marked_at_that_fill() -> None:
    ledger = Ledger(100_000, created_ts=OPENED)
    fill(ledger, 1, ts=DAY1, symbol="GRML", side="BUY", qty=100, price=8.80)
    out = history.build(ledger, venue="paper", range_key="ALL", now_ts=DAY1 + 100)
    buy_fees = for_fill("BUY", 100, 8.80).total
    assert set(out) == SHAPE and out["ledger_opened_at"] == iso_et(OPENED) and out["starting_cash"] == 100_000
    (bought,) = out["equity"]
    assert set(bought) == POINT and bought["ts"] == DAY1
    assert bought["cash"] == pytest.approx(100_000 - 880 - buy_fees)
    assert bought["net_liquidation"] == pytest.approx(100_000 - buy_fees)  # 100 GRML marked at 8.80, the fill
    assert (bought["unrealized"], bought["realized"]) == (0.0, pytest.approx(-buy_fees))
    (entry,) = out["fills"]
    assert set(entry) == FILL
    assert entry == {
        "ts": DAY1, "order_id": 1, "symbol": "GRML", "side": "BUY", "qty": 100.0, "price": 8.80,
        "source": "manual", "bot_id": None, "commission": 1.0, "fees": 0.0, "realized": pytest.approx(-buy_fees),
        "fill_estimated": True, "fill_basis": "live_quote",
    }
    # Selling half at 9.30 marks the 50 still held at 9.30 -- the last fill, never a quote.
    fill(ledger, 2, ts=DAY1 + 60, symbol="GRML", side="SELL", qty=50, price=9.30)
    sold = history.build(ledger, venue="paper", range_key="ALL", now_ts=DAY1 + 100)["equity"][-1]
    sell_fees = for_fill("SELL", 50, 9.30).total
    assert sold["unrealized"] == pytest.approx(50 * 0.50)
    assert sold["realized"] == pytest.approx(50 * 0.50 - buy_fees - sell_fees, abs=1e-3)
    assert sold["net_liquidation"] == pytest.approx(sold["cash"] + 50 * 9.30, abs=1e-3)


def test_a_rollover_is_an_equity_point_and_daily_rows_key_on_the_practice_day() -> None:
    ledger = Ledger(100_000, created_ts=OPENED)
    fill(ledger, 1, ts=DAY1, symbol="GRML", side="BUY", qty=100, price=8.80)
    fill(ledger, 2, ts=DAY1 + 60, symbol="GRML", side="SELL", qty=100, price=9.30)
    # 03:59 ET still belongs to the first practice day; the 04:00 rollover opens the second.
    fill(ledger, 3, ts=ROLLOVER - 60, symbol="GRML", side="BUY", qty=10, price=9.0)
    fill(ledger, 4, ts=DAY2, symbol="QNME", side="BUY", qty=10, price=14.0, source="bot", bot_id="momo-1")
    out = history.build(ledger, venue="paper", range_key="ALL", now_ts=DAY2 + 60)
    assert [(d["date"], d["fills"], d["archived"]) for d in out["daily"]] == [
        ("2026-09-21", 3, False), ("2026-09-22", 1, False),
    ]
    assert [p["ts"] for p in out["equity"]] == [DAY1, DAY1 + 60, ROLLOVER - 60, ROLLOVER, DAY2]  # event order
    points = {p["ts"]: p for p in out["equity"]}
    assert points[ROLLOVER] == {**points[ROLLOVER - 60], "ts": ROLLOVER}  # nothing moved at 04:00
    assert sum(d["realized"] for d in out["daily"]) == pytest.approx(out["components"]["realized"], abs=1e-3)
    assert sum(d["commissions"] + d["fees"] for d in out["daily"]) == pytest.approx(
        out["components"]["commissions"] + out["components"]["sec_finra_fees"], abs=1e-3,
    )
    assert out["components"]["unrealized"] == pytest.approx(out["equity"][-1]["unrealized"])


# ---------------------------------------------------------------- by source
def test_by_source_is_read_from_the_stamps_and_sums_to_realized() -> None:
    ledger = Ledger(100_000, created_ts=OPENED)
    fill(ledger, 1, ts=DAY1, symbol="GRML", side="BUY", qty=100, price=8.80)
    fill(ledger, 2, ts=DAY1 + 60, symbol="GRML", side="SELL", qty=100, price=9.30)
    fill(ledger, 3, ts=DAY1 + 120, symbol="QNME", side="BUY", qty=250, price=14.21, source="bot", bot_id="momo-1")
    fill(ledger, 4, ts=DAY1 + 180, symbol="QNME", side="SELL", qty=250, price=14.10, source="bot", bot_id="momo-1")
    out = history.build(ledger, venue="paper", range_key="1D", now_ts=DAY1 + 200)
    by = {(r["source"], r["bot_id"]): r for r in out["by_source"]}
    assert list(by) == [("manual", None), ("bot", "momo-1")]
    assert (by["manual", None]["fills"], by["bot", "momo-1"]["fills"]) == (2, 2)
    manual_fees = for_fill("BUY", 100, 8.80).total + for_fill("SELL", 100, 9.30).total
    bot_fees = for_fill("BUY", 250, 14.21).total + for_fill("SELL", 250, 14.10).total
    assert by["manual", None]["realized"] == pytest.approx(50.0 - manual_fees, abs=1e-3)
    assert by["bot", "momo-1"]["realized"] == pytest.approx(-27.5 - bot_fees, abs=1e-3)
    assert by["bot", "momo-1"]["commissions"] + by["bot", "momo-1"]["fees"] == pytest.approx(bot_fees, abs=1e-3)
    components = out["components"]
    assert sum(r["realized"] for r in out["by_source"]) == pytest.approx(components["realized"], abs=1e-3)
    assert components["realized"] == pytest.approx(ledger.realized, abs=1e-3)
    assert components["bot_realized"] == pytest.approx(by["bot", "momo-1"]["realized"])
    assert components["commissions"] == pytest.approx(sum(r["commissions"] for r in out["by_source"]), abs=1e-3)
    assert components["sec_finra_fees"] == pytest.approx(sum(r["fees"] for r in out["by_source"]), abs=1e-3)
    assert components["sec_finra_fees"] > 0 and components["unrealized"] == 0.0


# ------------------------------------------------------------------- ranges
def test_range_bounds_equity_fills_and_daily_at_the_practice_day_start() -> None:
    ledger = two_days()
    one = history.build(ledger, venue="paper", range_key="1D", now_ts=DAY2 + 60)
    assert one["range"] == "1D" and one["range_start"] == ROLLOVER
    assert [f["order_id"] for f in one["fills"]] == [3]
    assert [d["date"] for d in one["daily"]] == ["2026-09-22"]
    assert [p["ts"] for p in one["equity"]] == [ROLLOVER, DAY2]
    assert one["components"]["realized"] == pytest.approx(-for_fill("BUY", 10, 14.0).total)  # day 2 only
    assert [r["source"] for r in one["by_source"]] == ["bot"]
    five = history.build(ledger, venue="paper", range_key="5D", now_ts=DAY2 + 60)
    assert five["range_start"] == datetime(2026, 9, 18, 4, 0, tzinfo=ET).timestamp()
    assert [f["order_id"] for f in five["fills"]] == [1, 2, 3]
    ytd = history.build(ledger, venue="paper", range_key="ytd", now_ts=DAY2 + 60)
    assert ytd["range"] == "YTD" and ytd["range_start"] == datetime(2026, 1, 1, 4, 0, tzinfo=ET).timestamp()
    everything = history.build(ledger, venue="paper", range_key="ALL", now_ts=DAY2 + 60)
    assert everything["range_start"] is None and len(everything["equity"]) == 4
    with pytest.raises(history.RangeError):
        history.normalize_range("6M")


# ----------------------------------------------------------------- archives
def test_archived_ledgers_days_are_included_flagged_and_kept_out_of_this_ledgers_figures(tmp_path) -> None:
    broker = paper_broker(tmp_path, created_ts=DAY2 - 3600)
    old = Ledger(50_000, created_ts=OPENED)
    fill(old, 1, ts=DAY1, symbol="GRML", side="BUY", qty=100, price=8.80)
    fill(old, 2, ts=DAY1 + 60, symbol="GRML", side="SELL", qty=100, price=9.30)
    stamp = datetime(2026, 9, 21, 16, 12, 40, tzinfo=ET)
    persist.save(old, persist.archive_path(broker.persist_path, now=stamp))
    fill(broker.ledger, 1, ts=DAY2, symbol="QNME", side="BUY", qty=10, price=14.0)
    Clock.now = DAY2 + 60
    out = history.for_broker(broker, "ALL")
    assert [(d["date"], d["archived"], d["fills"]) for d in out["daily"]] == [
        ("2026-09-21", True, 2), ("2026-09-22", False, 1),
    ]
    (archive,) = out["archives"]
    assert set(archive) == {"file", "opened_at", "closed_at", "realized", "days"}
    assert archive["file"] == "practice-paper-20260921-161240.json"
    assert archive["opened_at"] == iso_et(OPENED) and datetime.fromisoformat(archive["closed_at"])
    assert (archive["realized"], archive["days"]) == (pytest.approx(old.realized, abs=1e-3), 1)
    assert out["warnings"] == []
    # The archive is another account: it never enters this ledger's equity, fills, split or components.
    assert [f["order_id"] for f in out["fills"]] == [1] and [p["ts"] for p in out["equity"]] == [DAY2]
    assert out["components"]["realized"] == pytest.approx(-for_fill("BUY", 10, 14.0).total)
    assert out["starting_cash"] == 100_000
    # 1D keeps the archived day out of ``daily`` like any other day outside the range.
    assert [d["date"] for d in history.for_broker(broker, "1D")["daily"]] == ["2026-09-22"]


def test_a_damaged_archive_is_skipped_with_a_warning_never_a_500(tmp_path, caplog) -> None:
    broker = paper_broker(tmp_path)
    (tmp_path / "practice-paper-20260101-000000.json").write_text("not json", encoding="utf-8")
    (tmp_path / "practice-paper-20260102-000000.json").write_text('{"schema_version": 99}', encoding="utf-8")
    persist.save(Ledger(100_000, created_ts=OPENED), str(tmp_path / "practice-paper-20260103-000000.json"))
    (tmp_path / ".practice-abc.tmp").write_text("{", encoding="utf-8")  # a write in flight is not an archive
    with caplog.at_level(logging.WARNING, logger="practice.history"):
        out = history.for_broker(broker, "ALL")
    assert [a["file"] for a in out["archives"]] == ["practice-paper-20260103-000000.json"]
    assert len(out["warnings"]) == 2
    assert out["warnings"][0].startswith("archive practice-paper-20260101-000000.json skipped")
    assert "schema_version 99" in out["warnings"][1]
    assert "practice-paper-20260101-000000.json" in caplog.text
    assert out["archives"][0]["days"] == 0 and out["daily"] == []


# ------------------------------------------------------------------- routes
def test_the_route_serves_paper_history_as_json(client) -> None:
    Clock.now = OPENED
    broker = practice_broker.for_venue("paper")
    fill(broker.ledger, 1, ts=DAY1, symbol="GRML", side="BUY", qty=100, price=8.80)
    Clock.now = DAY1 + 100
    res = client.get("/api/practice/history", params={"venue": "Paper", "range": "1d"})
    assert res.status_code == 200
    body = res.json()
    assert set(body) == SHAPE
    assert (body["venue"], body["account_id"], body["range"], body["schema_version"]) == ("paper", "NOVA-PAPER", "1D", 1)
    assert [f["symbol"] for f in body["fills"]] == ["GRML"] and body["fills"][0]["fill_estimated"] is True
    assert [d["date"] for d in body["daily"]] == ["2026-09-21"]
    assert body["archives"] == [] and body["warnings"] == []
    default = client.get("/api/practice/history", params={"venue": "paper"})
    assert default.status_code == 200 and default.json()["range"] == "1D"


def test_sim_with_nothing_loaded_is_the_shape_with_empty_lists(client) -> None:
    res = client.get("/api/practice/history", params={"venue": "sim"})
    assert res.status_code == 200
    body = res.json()
    assert set(body) == SHAPE
    assert (body["venue"], body["account_id"], body["range"], body["schema_version"]) == ("sim", "NOVA-SIM", "1D", 1)
    assert body["starting_cash"] == 100_000 and body["range_start"] is not None
    assert (body["equity"], body["fills"], body["by_source"], body["daily"]) == ([], [], [], [])
    assert (body["archives"], body["warnings"]) == ([], [])
    assert body["components"] == {
        "realized": 0.0, "unrealized": 0.0, "commissions": 0.0, "sec_finra_fees": 0.0, "bot_realized": 0.0,
    }


def test_an_unknown_venue_or_range_is_a_400_and_a_missing_venue_a_422(client) -> None:
    assert client.get("/api/practice/history", params={"venue": "live"}).status_code == 400
    bad_range = client.get("/api/practice/history", params={"venue": "paper", "range": "6M"})
    assert bad_range.status_code == 400 and "6M" in bad_range.json()["detail"]
    assert client.get("/api/practice/history").status_code == 422
