"""Paper's round trips in the Reports journal (ADR 069 decision 6, #1267): one per holder, built from the practice
ledger's own split and each at its holder's own cost; written once per ledger change and never deleted; read by
venue and view, with yours and the bots' beside each total. The risk engine and the metrics never read one."""
from __future__ import annotations

import pytest

import journal.db as db
from journal import paper_trips, split, store
from journal.metrics import compute_metrics
from practice.fees import Fees
from practice.ledger import Ledger

T0 = 1_790_000_000.0          # 2026-09-21, 09:33 ET
FEE = Fees(commission=1.0)
LT = {"source": "bot", "origin": "live_trader"}
LT_CLOSE = {"source": "flatten", "origin": "live_trader"}
CLAUDE = {"source": "bot", "origin": "claude"}


@pytest.fixture(autouse=True)
def journal(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "cache_dir", lambda: tmp_path)
    db.init_db()
    paper_trips.reset_for_tests()
    yield
    paper_trips.reset_for_tests()


class _Ids:
    def __init__(self) -> None:
        self.next = 0

    def __call__(self) -> int:
        self.next += 1
        return self.next


def _ledger() -> tuple[Ledger, _Ids]:
    return Ledger(100_000, created_ts=T0, split_owners=True), _Ids()


def place(ledger: Ledger, ids: _Ids, symbol: str, side: str, qty: float, *, source: str = "manual",
          origin: str | None = None, **row) -> int:
    oid = ids()
    ledger.place({"order_id": oid, "symbol": symbol, "side": side, "qty": qty, "order_origin": origin,
                  "order_type": "LMT", **row}, ts=T0 + oid, source=source)
    return oid


def trade(ledger: Ledger, ids: _Ids, symbol: str, side: str, qty: float, price: float, **kw) -> int:
    oid = place(ledger, ids, symbol, side, qty, **kw)
    ledger.fill(oid, ts=T0 + 0.5 + oid, price=price, basis="test", fees=FEE)
    return oid


def stop_leg(ledger: Ledger, ids: _Ids, entry: int, symbol: str, side: str, qty: float, stop: float) -> int:
    return place(ledger, ids, symbol, side, qty, order_type="STP", stop_price=stop, parent_id=entry,
                 leg_role="stop")


class _Broker:
    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger
        self.persist_path = None


@pytest.fixture
def paper(monkeypatch):
    """A Paper broker holding the test's ledger, for the routes' and ``sync``'s own reads."""
    import practice.broker as broker_mod

    ledger, ids = _ledger()
    broker = _Broker(ledger)
    monkeypatch.setattr(broker_mod, "for_venue", lambda venue: broker)
    return ledger, ids


# ------------------------------------------------------------- one per holder
def test_two_holders_in_one_stock_are_two_trades_each_at_its_own_cost() -> None:
    ledger, ids = _ledger()
    trade(ledger, ids, "SOFI", "BUY", 100, 10.0)
    trade(ledger, ids, "SOFI", "BUY", 100, 12.0, **LT)
    trade(ledger, ids, "SOFI", "SELL", 100, 11.0)                 # you sell yours
    trade(ledger, ids, "SOFI", "SELL", 100, 13.0, **LT_CLOSE)     # the Live Trader its own
    trips = {t["owner"]: t for t in paper_trips.round_trips(ledger)}
    assert set(trips) == {"you", "earlier_bots"}
    yours, its = trips["you"], trips["earlier_bots"]
    assert (yours["bot"], yours["side"], yours["qty"], yours["entry_price"], yours["exit_price"]) == \
        (None, "long", 100, 10.0, 11.0)
    assert (its["bot"], its["entry_price"], its["exit_price"]) == ("live_trader", 12.0, 13.0)
    assert yours["pnl"] == pytest.approx(100 - 2.0)               # net of its two commissions
    assert its["pnl"] == pytest.approx(100 - 2.0)
    assert yours["commission"] == pytest.approx(2.0)
    assert sum(t["pnl"] for t in trips.values()) == pytest.approx(ledger.realized)


def test_novas_own_close_closes_each_holders_own_trade() -> None:
    ledger, ids = _ledger()
    trade(ledger, ids, "ABC", "BUY", 100, 10.0)
    trade(ledger, ids, "ABC", "BUY", 50, 10.0, **LT)
    trade(ledger, ids, "ABC", "SELL", 150, 11.0, source="kill")   # KILL: no owner, closes both
    trips = paper_trips.round_trips(ledger)
    assert sorted((t["owner"], t["qty"]) for t in trips) == [("earlier_bots", 50), ("you", 100)]


def test_a_short_round_trip_and_a_position_still_open() -> None:
    ledger, ids = _ledger()
    trade(ledger, ids, "XYZ", "SELL", 100, 5.0, short_entry=True)
    trade(ledger, ids, "XYZ", "BUY", 40, 4.0)
    assert paper_trips.round_trips(ledger) == []                  # 60 still short: not a trade yet
    trade(ledger, ids, "XYZ", "BUY", 60, 4.5)
    (trip,) = paper_trips.round_trips(ledger)
    assert (trip["side"], trip["qty"], trip["entry_price"]) == ("short", 100, 5.0)
    assert trip["exit_price"] == pytest.approx((40 * 4.0 + 60 * 4.5) / 100)


def test_the_stop_is_the_leg_sent_with_the_entry_on_the_losing_side() -> None:
    ledger, ids = _ledger()
    entry = trade(ledger, ids, "AAA", "BUY", 100, 10.0, **CLAUDE)
    stop_leg(ledger, ids, entry, "AAA", "SELL", 100, 9.5)
    trade(ledger, ids, "AAA", "SELL", 100, 11.0, source="flatten", origin="claude")
    wrong = trade(ledger, ids, "BBB", "BUY", 100, 10.0)
    stop_leg(ledger, ids, wrong, "BBB", "SELL", 100, 10.5)        # above a long's entry: plans no risk
    trade(ledger, ids, "BBB", "SELL", 100, 11.0)
    trade(ledger, ids, "CCC", "BUY", 100, 10.0)
    trade(ledger, ids, "CCC", "SELL", 100, 11.0)                  # sent with no stop
    stops = {t["symbol"]: t["stop_price"] for t in paper_trips.round_trips(ledger)}
    assert stops == {"AAA": 9.5, "BBB": None, "CCC": None}


def test_close_keys_name_the_ledger_the_holder_and_the_opening_fill() -> None:
    ledger, ids = _ledger()
    trade(ledger, ids, "ABC", "BUY", 10, 1.0)
    trade(ledger, ids, "ABC", "SELL", 10, 1.1)
    trade(ledger, ids, "ABC", "BUY", 10, 1.0)
    trade(ledger, ids, "ABC", "SELL", 10, 1.2)
    keys = [t["close_key"] for t in paper_trips.round_trips(ledger)]
    assert len(set(keys)) == 2
    assert all(k.startswith(f"paper:{T0:.0f}:you:ABC:") for k in keys)


# ------------------------------------------------------------------ the sync
def test_a_sync_writes_once_and_a_rewrite_keeps_the_tags() -> None:
    ledger, ids = _ledger()
    trade(ledger, ids, "ABC", "BUY", 100, 10.0)
    trade(ledger, ids, "ABC", "SELL", 100, 11.0)
    assert paper_trips.sync_ledgers([ledger]) == 1
    assert paper_trips.sync_ledgers([ledger]) == 0                # nothing new: nothing written
    (stored,) = store.get_closed_trades(venue="paper")
    assert (stored["venue"], stored["owner"], stored["bot"]) == ("paper", "you", None)
    store.update_trade_tags(stored["id"], ["first pullback"])
    (row,) = paper_trips.round_trips(ledger)
    assert store.upsert_round_trips([{**row, "pnl": 12.5}], venue="paper") == 1
    (again,) = store.get_closed_trades(venue="paper")
    assert (again["id"], again["pnl"], again["tags"]) == (stored["id"], 12.5, ["first pullback"])


def test_sync_reads_the_paper_ledger_once_per_change(paper) -> None:
    ledger, ids = paper
    trade(ledger, ids, "ABC", "BUY", 100, 10.0)
    trade(ledger, ids, "ABC", "SELL", 100, 11.0)
    assert paper_trips.sync() == 1
    assert paper_trips.sync() == 0
    trade(ledger, ids, "ABC", "BUY", 100, 10.0, **LT)
    trade(ledger, ids, "ABC", "SELL", 100, 10.5, **LT_CLOSE)
    assert paper_trips.sync() == 1
    assert [t["bot"] for t in store.get_closed_trades(venue="paper")] == [None, "live_trader"]


# ------------------------------------------------------- reading by the view
def _live_trade(symbol: str = "LIVE") -> int:
    return store.record_trade(symbol, None, "long", 10, 1.0, None, None, 1.5, 5.0, None,
                              opened_ts=T0, closed_ts=T0 + 60)


def _books(ledger: Ledger, ids: _Ids) -> None:
    trade(ledger, ids, "AAA", "BUY", 100, 10.0)
    trade(ledger, ids, "AAA", "SELL", 100, 11.0)
    trade(ledger, ids, "BBB", "BUY", 100, 10.0, **LT)
    trade(ledger, ids, "BBB", "SELL", 100, 9.0, **LT_CLOSE)
    entry = trade(ledger, ids, "CCC", "BUY", 100, 10.0, **CLAUDE)
    stop_leg(ledger, ids, entry, "CCC", "SELL", 100, 9.0)
    trade(ledger, ids, "CCC", "SELL", 100, 12.0, source="flatten", origin="claude")


def test_the_venue_and_the_view_pick_the_rows() -> None:
    ledger, ids = _ledger()
    _books(ledger, ids)
    paper_trips.sync_ledgers([ledger])
    _live_trade()
    symbols = lambda **kw: sorted(t["symbol"] for t in store.get_closed_trades(**kw))  # noqa: E731
    assert symbols() == ["LIVE"]                                   # the journal as it was
    assert symbols(venue="paper") == ["AAA", "BBB", "CCC"]
    assert symbols(venue="paper", owner="you") == ["AAA"]
    assert symbols(venue="paper", owner="earlier_bots") == ["BBB"]
    assert symbols(venue="paper", owner="claude") == ["CCC"]
    assert symbols(venue="paper", owner="brain") == []
    assert symbols(venue="paper", bot="live_trader") == ["BBB"]
    assert [t["symbol"] for t in store.get_trades(venue="paper", owner="claude", limit=1)] == ["CCC"]


def test_the_risk_engine_and_the_metrics_never_read_a_paper_trade() -> None:
    ledger, ids = _ledger()
    _books(ledger, ids)
    paper_trips.sync_ledgers([ledger])
    _live_trade()
    assert compute_metrics()["total_closed_trades"] == 1
    assert [t["symbol"] for t in store.get_closed_trades(include_mock=True)] == ["LIVE"]


def test_holders_list_the_books_in_order_then_the_retired_bots_by_count() -> None:
    trades = [{"owner": "claude", "bot": None}, {"owner": "earlier_bots", "bot": "live_trader"},
              {"owner": "earlier_bots", "bot": "live_trader"}, {"owner": None, "bot": None},
              {"owner": "earlier_bots", "bot": "auto_entry"}]
    assert split.holders(trades) == [
        {"owner": "you", "bot": None, "trade_count": 1},
        {"owner": "claude", "bot": None, "trade_count": 1},
        {"owner": "earlier_bots", "bot": "live_trader", "trade_count": 2},
        {"owner": "earlier_bots", "bot": "auto_entry", "trade_count": 1},
    ]


# ----------------------------------------------------------------- the routes
def test_the_all_view_carries_every_book_beside_each_total(paper) -> None:
    from routes.journal import journal_calendar, journal_drawdown, journal_r_multiples, journal_tags

    ledger, ids = paper
    _books(ledger, ids)
    _live_trade()
    year = journal_calendar(year=2026, month=None, include_mock=False, venue="paper")
    assert (year["venue"], year["view"]) == ("paper", {"owner": None, "bot": None})
    assert year["year_trade_count"] == 3
    assert year["by_owner"]["you"] == {"pnl": pytest.approx(98.0), "trade_count": 1}
    assert (year["by_owner"]["claude"]["trade_count"], year["by_owner"]["earlier_bots"]["trade_count"]) == (1, 1)
    assert year["by_owner"]["brain"] == {"pnl": 0.0, "trade_count": 0}
    september = year["months"][8]
    assert september["by_owner"]["earlier_bots"]["trade_count"] == 1
    assert all("by_owner" in day for day in september["days"])
    assert [(h["owner"], h["bot"]) for h in year["holders"]] == [("you", None), ("claude", None),
                                                                 ("earlier_bots", "live_trader")]
    month = journal_calendar(year=2026, month=9, include_mock=False, venue="paper")
    assert month["by_owner"]["you"]["trade_count"] == 1
    assert all("by_owner" in week for week in month["weeks"])
    r = journal_r_multiples(include_mock=False, venue="paper")
    assert r["by_owner"]["you"]["skipped_no_stop"] == 1
    assert (r["by_owner"]["claude"]["scored_count"], r["by_owner"]["claude"]["trade_count"]) == (1, 1)
    assert (r["by_owner"]["earlier_bots"]["scored_count"], r["by_owner"]["earlier_bots"]["trade_count"]) == (0, 1)
    dd = journal_drawdown(include_mock=False, venue="paper")
    assert [p["owner"] for p in dd["curve"]] == ["you", "earlier_bots", "claude"]
    assert set(dd["by_owner"]) == {"you", "claude", "brain", "earlier_bots"}
    assert journal_tags(include_mock=False, venue="paper")["venue"] == "paper"


def test_one_book_reads_alone_and_live_reads_as_before(paper) -> None:
    from routes.journal import journal_calendar, journal_r_multiples

    ledger, ids = paper
    _books(ledger, ids)
    _live_trade()
    yours = journal_calendar(year=2026, month=None, include_mock=False, venue="paper", owner="you")
    assert yours["year_trade_count"] == 1 and "by_owner" not in yours
    assert len(yours["holders"]) == 3                              # the switch still counts everyone
    claude = journal_calendar(year=2026, month=None, include_mock=False, venue="paper", owner="claude")
    assert claude["view"] == {"owner": "claude", "bot": None} and claude["year_trade_count"] == 1
    lt = journal_calendar(year=2026, month=None, include_mock=False, venue="paper", bot="live_trader")
    assert lt["view"] == {"owner": "earlier_bots", "bot": "live_trader"} and lt["year_trade_count"] == 1
    live = journal_calendar(year=2026, month=None, include_mock=False)
    assert live["year_trade_count"] == 1 and "holders" not in live and "by_owner" not in live
    assert "by_owner" not in journal_r_multiples(include_mock=False, venue="paper", owner="claude")
