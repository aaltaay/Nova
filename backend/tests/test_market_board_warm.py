"""The Market page is ready before it opens, and no block is left empty (ADR 053 amendment 2026-10-13 evening).

The operator at 17:38 ET: "empty widgets, the symbols are not clickable ... the runners per session is so tiny",
then "this need to load while all other items in this app need to run ... when you close, it's pretty slow to
load". Measured that evening: the 7 D / 30 D numbers reached the page 509-632 s after it opened, the futures read
"--" through CME's 17:00-18:00 ET pause, breadth lost volume and TRIN after the close, two sectors' top-stock cards
were empty and the biggest-names read timed out. These pin each fix.
"""
from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import constants_market_board as cmb
from market_board import board, breadth, clock, disk, ibkr_reads, jobs, keep, refresh, sectors
from market_board.state import Store, store

DAY = date(2026, 10, 13)


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("NOVA_LEADERBOARD_DIR", str(tmp_path / "lb"))
    monkeypatch.delenv(cmb.MARKET_WARM_ENV, raising=False)
    refresh.reset_for_tests()
    breadth.reset_for_tests()
    yield
    refresh.reset_for_tests()
    breadth.reset_for_tests()


def _wire(monkeypatch, calls: list[str]) -> None:
    monkeypatch.setattr(ibkr_reads, "ready", lambda: True)
    monkeypatch.setattr(ibkr_reads, "headroom_ok", lambda: True)
    monkeypatch.setattr(refresh, "breadth_due", lambda now: False)

    def fake(name, value):
        def run(*args, **kwargs):
            calls.append(name)
            return value
        return run

    monkeypatch.setattr(ibkr_reads, "reference_quotes", fake("quotes", {}))
    monkeypatch.setattr(ibkr_reads, "stock_quotes", fake("stocks", {}))
    monkeypatch.setattr(ibkr_reads, "movers", fake("movers", []))
    monkeypatch.setattr(ibkr_reads, "prior_close", fake("prior", {"date": "2099-01-01", "close": 1.0}))
    monkeypatch.setattr(ibkr_reads, "line_bars", fake("line", []))
    monkeypatch.setattr(ibkr_reads, "rth_closes", fake("closes", [["2099-01-01", 1.0]]))


def _holdings(**rows: list[str]) -> None:
    now = time.time()
    for etf, syms in rows.items():
        store().put(f"holdings:{etf}", "ssga", {"etf": etf, "as_of": "2026-10-13", "fetched_at": now,
                                                "rows": [{"symbol": s, "name": None, "weight_pct": 1.0} for s in syms]},
                    now)


# -- warm: the reads run while nobody looks -------------------------------------------------------------------------

def test_reads_run_with_the_page_closed(monkeypatch):
    calls: list[str] = []
    _wire(monkeypatch, calls)
    now = time.time()
    assert not store().wanted(now)
    assert refresh.run_once("ibkr", now)
    assert calls == ["quotes"]
    assert refresh.run_once("history", now)


def test_warm_off_reads_only_while_the_page_asks(monkeypatch):
    calls: list[str] = []
    _wire(monkeypatch, calls)
    monkeypatch.setenv(cmb.MARKET_WARM_ENV, "0")
    now = time.time()
    assert not refresh.run_once("ibkr", now)
    assert not refresh.run_once("history", now)
    assert not refresh.run_once("files", now)
    store().want(now)
    assert refresh.run_once("ibkr", now)
    assert calls == ["quotes"]


def test_with_nobody_looking_each_read_keeps_its_slower_cadence(monkeypatch):
    calls: list[str] = []
    _wire(monkeypatch, calls)
    now = time.time()
    store().put("quotes", "ibkr", {}, now - 30)
    quotes = next(j for j in jobs.ibkr_jobs(now) if j.key == "quotes")
    assert quotes.ttl_now(True) == cmb.MARKET_QUOTES_TTL_SEC
    assert quotes.ttl_now(False) == cmb.MARKET_IDLE_QUOTES_TTL_SEC
    assert refresh._due(quotes, now, wanted=True)         # 30 s old: the page wants it every 10 s
    assert not refresh._due(quotes, now, wanted=False)    # nobody looks: every 60 s
    assert refresh._due(quotes, now + 31, wanted=False)


def test_every_idle_cadence_is_slower_than_the_page_and_younger_than_stale():
    for idle, page in ((cmb.MARKET_IDLE_QUOTES_TTL_SEC, cmb.MARKET_QUOTES_TTL_SEC),
                       (cmb.MARKET_IDLE_ETF_TTL_SEC, cmb.MARKET_ETF_TTL_SEC),
                       (cmb.MARKET_IDLE_MOVERS_TTL_SEC, cmb.MARKET_MOVERS_TTL_SEC),
                       (cmb.MARKET_IDLE_POOL_TTL_SEC, cmb.MARKET_HOLDINGS_QUOTES_TTL_SEC),
                       (cmb.MARKET_IDLE_LINES_TTL_SEC, cmb.MARKET_LINES_TTL_SEC),
                       (cmb.MARKET_IDLE_CLIMATE_TTL_SEC, cmb.MARKET_CLIMATE_TTL_SEC)):
        assert page <= idle
        # A warm answer is never so old that the store drops it before the next one lands.
        assert idle < cmb.MARKET_STALE_MAX_SEC


def test_a_page_ask_still_wakes_every_lane(monkeypatch):
    started: list[str] = []
    monkeypatch.setattr(refresh, "_loop", lambda lane: started.append(lane))
    monkeypatch.setattr(refresh, "_threads", {})
    refresh.want(time.time())
    deadline = time.time() + 2
    while len(started) < len(refresh.LANES) and time.time() < deadline:
        time.sleep(0.01)
    assert sorted(started) == sorted(refresh.LANES)
    assert store().wanted(time.time())


# -- the biggest names: always, in chunks ----------------------------------------------------------------------------

def test_the_biggest_names_are_read_always_in_chunks_with_tile_quotes_first(monkeypatch):
    calls: list[str] = []
    _wire(monkeypatch, calls)
    _holdings(XLK=["NVDA", "MSFT", "AAPL", "AVGO", "ORCL", "CRM"], XLU=["NEE", "SO", "DUK", "CEG", "AEP"],
              XLV=["LLY", "JNJ", "ABBV", "UNH", "MRK"])
    now = time.time()
    keys = [j.key for j in jobs.ibkr_jobs(now)]
    assert keys[:3] == ["quotes", "etf_quotes", "movers"]
    chunks = jobs.pool_chunks()
    assert all(len(c) <= cmb.MARKET_POOL_CHUNK for c in chunks)
    # MARKET_SECTORS order (XLV before XLU), each sector's top MARKET_LEADER_POOL holdings.
    assert sum(chunks, []) == ["NVDA", "MSFT", "AAPL", "AVGO", "ORCL", "LLY", "JNJ", "ABBV", "UNH", "MRK",
                               "NEE", "SO", "DUK", "CEG", "AEP"]
    assert keys[3:] == [f"pool_quotes:{i}" for i in range(len(chunks))]


def test_tile_quotes_run_between_biggest_name_chunks(monkeypatch):
    calls: list[str] = []
    _wire(monkeypatch, calls)
    _holdings(XLK=[f"S{i}" for i in range(5)], XLU=[f"U{i}" for i in range(5)], XLV=[f"V{i}" for i in range(5)])
    t = time.time()
    store().want(t)
    for _ in range(4):
        assert refresh.run_once("ibkr", t)
    # The tiles, the ETFs, the scan (and its picks' prices), the first chunk of biggest names.
    assert calls == ["quotes", "stocks", "movers", "stocks", "stocks"]
    t += cmb.MARKET_QUOTES_TTL_SEC + 1                            # the tiles are due again before the next chunk
    store().want(t)
    assert refresh.run_once("ibkr", t)
    assert calls[-1] == "quotes"


def test_store_merges_chunks_by_their_own_age():
    st = Store()
    now = 10_000.0
    st.put("pool_quotes:0", "ibkr", {"NVDA": {"price": 1.0}}, now)
    st.put("pool_quotes:1", "ibkr", {"LLY": {"price": 2.0}}, now - cmb.MARKET_STALE_MAX_SEC - 1)   # too old
    st.put("pool_quotesX", "ibkr", {"BAD": {}}, now)
    assert st.merged("pool_quotes:", now) == {"NVDA": {"price": 1.0}}


# -- kept across restarts ------------------------------------------------------------------------------------------

def test_answers_kept_on_disk_come_back_at_their_own_time():
    st = Store()
    now = time.time()
    st.put("closes:XLK", "ibkr", [["2026-10-12", 280.0]], now - 600)
    st.put("line:es", "ibkr", [[now - 300, 6840.0]], now - 300)
    st.put("holdings:XLK", "ssga", {"rows": []}, now)       # already a file of its own: not kept here
    st.put("climate", "leaderboard", [], now)              # local and quick: read again
    assert keep.save(st, now) == 2
    fresh = Store()
    assert keep.load(fresh, now + 5) == 2
    assert fresh.answered_at("closes:XLK") == pytest.approx(now - 600)
    assert fresh.get("closes:XLK", now, 86400) == [["2026-10-12", 280.0]]
    assert fresh.get("holdings:XLK", now) is None and fresh.get("climate", now) is None
    assert not fresh.tried("closes:XLK")                 # restored, not asked: the source is still "not asked yet"


def test_a_kept_answer_never_replaces_a_newer_one():
    st = Store()
    now = time.time()
    st.put("quotes", "ibkr", {"es": {"last": 1.0}}, now - 100)
    keep.save(st, now - 100)
    live = Store()
    live.put("quotes", "ibkr", {"es": {"last": 2.0}}, now)
    assert keep.load(live, now) == 0
    assert live.get("quotes", now)["es"]["last"] == 2.0


def test_old_foreign_or_unknown_entries_are_ignored():
    now = time.time()
    disk.write(cmb.MARKET_KEEP_FILE, {"saved_at": now, "entries": {
        "closes:OLD": {"at": now - cmb.MARKET_KEEP_MAX_AGE_SEC - 1, "value": []},
        "climate": {"at": now, "value": []},
        "line:es": {"at": "yesterday", "value": []},
        "prior:es": {"at": now + 3600, "value": {}},       # from the future: a clock that jumped
        "closes:XLK": {"at": now - 60, "value": [["2026-10-12", 1.0]]},
    }})
    st = Store()
    assert keep.load(st, now) == 1
    assert st.get("closes:XLK", now, 86400) == [["2026-10-12", 1.0]]
    disk.write(cmb.MARKET_KEEP_FILE, {"schema_version": 99, "entries": {}})
    (disk.folder() / cmb.MARKET_KEEP_FILE).write_text('{"schema_version": 99, "entries": {"closes:X": '
                                                      '{"at": 1, "value": []}}}', encoding="utf-8")
    assert keep.load(Store(), now) == 0


def test_the_kept_file_is_written_only_when_something_changed_and_not_too_often():
    st = Store()
    now = time.time()
    keep.load_once(st, now)                              # nothing kept yet; this process's version is the baseline
    assert not keep.maybe_save(st, now)                  # nothing answered: nothing to write
    st.put("quotes", "ibkr", {}, now)
    assert keep.maybe_save(st, now)
    st.put("quotes", "ibkr", {}, now + 1)
    assert not keep.maybe_save(st, now + 1)              # changed, but within MARKET_KEEP_SAVE_SEC
    assert keep.maybe_save(st, now + cmb.MARKET_KEEP_SAVE_SEC + 1)
    assert not keep.maybe_save(st, now + 3 * cmb.MARKET_KEEP_SAVE_SEC)   # nothing new since


def test_the_first_start_restores_before_any_read(monkeypatch):
    now = time.time()
    st = Store()
    st.put("closes:XLK", "ibkr", [["2026-10-12", 280.0]], now - 60)
    keep.save(st, now - 60)
    store().reset()
    keep.reset_for_tests()
    monkeypatch.setattr(refresh, "_loop", lambda lane: None)
    monkeypatch.setattr(refresh, "_threads", {})
    refresh.start_breadth_sampler()
    assert store().get("closes:XLK", now, 86400) == [["2026-10-12", 280.0]]
    store().reset()
    refresh.start_breadth_sampler()                      # once per process: a later start reads nothing again
    assert store().get("closes:XLK", now, 86400) is None


def test_the_store_version_moves_with_every_answer():
    st = Store()
    v0 = st.version()
    st.put("quotes", "ibkr", {}, 1.0)
    assert st.version() == v0 + 1
    assert st.restore("closes:A", [], 0.5)
    assert st.version() == v0 + 1                        # a restored answer is not a new one


# -- the tiles ------------------------------------------------------------------------------------------------------

ES = {"id": "es", "label": "S&P 500 futures", "symbol": "ES", "sec_type": "CONTFUT", "exchange": "CME"}


def test_a_future_in_cmes_daily_pause_shows_its_last_bar_stale_with_its_time():
    bar = clock.at(DAY, 16 * 60 + 55)
    now = clock.at(DAY, 17 * 60 + 38)                    # 17:38 ET, the operator's screenshot
    line = [[clock.at(DAY, 16 * 60 + 50), 7854.0], [bar, 7855.5]]
    q = board._from_bars({"id": "es", "last": None, "prev_close": 7858.0, "data_type": "live"}, line, None, now)
    assert q["last"] == 7855.5 and q["at"] == bar and q["stale"] is True and q["data_type"] == "bars"
    tile = board._tile(ES, q, line, DAY, now)
    assert tile["last"] == 7855.5 and tile["change"] == pytest.approx(-2.5) and tile["stale"] is True
    assert tile["line"][-1][0] == bar                    # a stale price is not drawn on to now


def test_a_fresh_bar_is_not_stale_and_a_live_price_ends_the_line_at_now():
    now = clock.at(DAY, 10 * 60 + 2)
    line = [[clock.at(DAY, 10 * 60), 6842.5]]
    q = board._from_bars(None, line, {"close": 6800.25}, now)
    assert q["stale"] is False
    live = board._tile(ES, {"last": 6843.0, "prev_close": 6800.25}, line, DAY, now)
    assert live["stale"] is False and live["line"][-1] == [now, 6843.0]


def test_a_tile_with_no_bar_and_no_trade_stays_unknown():
    assert board._from_bars(None, [], {"close": 1.0}, 1e9) is None
    tile = board._tile(ES, None, None, DAY, clock.at(DAY, 12 * 60))
    assert tile["last"] is None and tile["change_pct"] is None and tile["stale"] is False


def test_the_small_caps_spread_is_stale_when_a_leg_is():
    es = {"change_pct": 0.1, "prev_close": 100.0, "line": [], "data_type": "bars", "at": 1, "stale": True}
    rty = {"change_pct": 0.5, "prev_close": 50.0, "line": [], "data_type": "bars", "at": 1, "stale": False}
    spread = board._spread({"es": es, "rty": rty}, {"id": "small_caps", "label": "x", "symbol": "RTY - ES"})
    assert spread["change_pct"] == pytest.approx(0.4) and spread["stale"] is True


def test_a_coin_asks_two_days_of_bars(monkeypatch):
    from ibkr import client, historical_service
    from market_board import contracts

    asked: list[str] = []

    async def bars(key, contract, *, duration, bar_size, what_to_show, use_rth):
        asked.append(f"{key}:{duration}:{what_to_show}")
        return [{"t": 1.0, "close": 2.0}]

    async def resolve(ib, spec, day):
        return object()

    monkeypatch.setattr(client, "get_ib", lambda: object())
    monkeypatch.setattr(contracts, "resolve", resolve)
    monkeypatch.setattr(historical_service, "request_reference_bars", bars)
    import asyncio
    monkeypatch.setattr(ibkr_reads, "_run", lambda coro, timeout, label: asyncio.run(coro))
    btc = next(s for s in cmb.MARKET_QUOTES if s["id"] == "btc")
    assert ibkr_reads.line_bars(btc, "2026-10-13") == [[1.0, 2.0]]
    ibkr_reads.line_bars(ES, "2026-10-13")
    assert asked == [f"CRYPTO:BTC:{cmb.MARKET_LINE_DURATION_CRYPTO}:AGGTRADES",
                     f"CONTFUT:ES:{cmb.MARKET_LINE_DURATION}:TRADES"]


# -- breadth after the close ---------------------------------------------------------------------------------------

def test_breadth_after_the_close_keeps_volume_and_trin():
    t = clock.at(DAY, 15 * 60 + 59)
    sample = {"advancing": 1540.0, "declining": 1226.0, "unchanged": 66.0, "up_volume": 1.92e9,
              "down_volume": 2.07e9, "tick": -146.0, "trin": 1.35, "data_type": "live", "at": t}
    breadth.record(sample, DAY, t)
    got = breadth.compose(clock.at(DAY, 17 * 60 + 38), DAY, "after_hours", None, None)
    assert got["state"] == "ok"
    assert (got["advancing"], got["up_volume"], got["down_volume"], got["trin"]) == (1540.0, 1.92e9, 2.07e9, 1.35)
    assert got["unchanged"] == 66.0 and got["tick"] == -146.0


def test_breadth_from_a_line_never_borrows_another_days_volume():
    old = clock.at(date(2026, 10, 12), 15 * 60 + 59)
    breadth.record({"advancing": 1.0, "declining": 2.0, "up_volume": 9.0, "down_volume": 9.0, "tick": 0.0,
                    "trin": 9.0, "at": old}, date(2026, 10, 12), old)
    t = clock.at(DAY, 15 * 60 + 59)
    breadth.reset_for_tests()
    # Today's line only (as a restart that kept today's samples but wrote no last file today would leave it).
    disk.write(f"breadth-{DAY.isoformat()}.json", {"date": DAY.isoformat(), "line_since": t,
                                                    "samples": [[t, 1540.0, 1226.0, -146.0]]})
    got = breadth.compose(clock.at(DAY, 17 * 60), DAY, "after_hours", None, None)
    assert got["advancing"] == 1540.0 and got["up_volume"] is None and got["trin"] is None


# -- every sector, every card filled ----------------------------------------------------------------------------------

def _ctx(movers: dict | None = None, pool: dict | None = None, etf: dict | None = None, closes=None) -> dict:
    members = {"XLK": ["NVDA", "MSFT", "AAPL", "AVGO", "ORCL", "CRM", "AMD"], "XLU": ["NEE", "SO", "DUK", "CEG", "AEP"],
               "XLV": ["LLY", "JNJ", "ABBV", "UNH", "MRK", "ABT"]}
    return {
        "today": "2026-10-13",
        "etf_quotes": etf if etf is not None else {"XLK": {"price": 101.0, "prev_close": 100.0},
                                                   "XLU": {"price": 99.0, "prev_close": 100.0},
                                                   "XLV": {"price": 98.7, "prev_close": 100.0}},
        "closes": closes or (lambda s: None),
        "holdings": lambda etf_: {"rows": [{"symbol": s} for s in members.get(etf_, [])]},
        "movers": movers or {},
        "pool_quotes": pool or {},
        "period_from": {"1D": "2026-10-13", "7D": "2026-10-07", "30D": "2026-09-14"},
    }


def _q(price: float, prev: float = 100.0) -> dict:
    return {"price": price, "prev_close": prev}


def test_every_sector_gets_a_card():
    got = sectors.top("movers", "1D", _ctx(), None)
    assert len(got["cards"]) == len(cmb.MARKET_SECTORS) == cmb.MARKET_TOP_CARDS
    assert got["cards"][0]["etf"] == "XLK"                # strongest first
    assert got["why"] == "IBKR has not priced the sectors' stocks yet"


def test_a_red_sector_with_no_scan_mover_is_filled_from_its_biggest_names():
    pool = {"LLY": _q(99.5), "JNJ": _q(98.0), "ABBV": _q(101.2), "UNH": _q(97.0), "MRK": _q(99.0),
            "NEE": _q(100.4)}
    movers = {"AMD": _q(105.0), "NVDA": _q(103.0)}
    got = sectors.top("movers", "1D", _ctx(movers, pool), None)
    by = {c["etf"]: c for c in got["cards"]}
    assert [r["symbol"] for r in by["XLV"]["rows"]] == ["ABBV", "LLY", "MRK", "JNJ", "UNH"]   # strongest first
    assert [r["symbol"] for r in by["XLK"]["rows"]][:2] == ["AMD", "NVDA"]                  # the scan's movers lead
    assert [r["symbol"] for r in by["XLU"]["rows"]] == ["NEE"]
    assert got["why"] is None


def test_the_leader_is_the_best_of_the_scan_and_the_biggest_names():
    pool = {"LLY": _q(99.5), "ABBV": _q(101.2)}
    rows = {r["etf"]: r for r in sectors.board("sectors", "1D", _ctx({"AMD": _q(105.0)}, pool))["rows"]}
    assert rows["XLV"]["leader"] == {"symbol": "ABBV", "change_pct": 1.2}
    assert rows["XLK"]["leader"] == {"symbol": "AMD", "change_pct": 5.0}
    assert rows["XLU"]["leader"] is None and rows["XLU"]["leader_why"] == "IBKR has not priced its stocks yet"
    themes = {r["etf"]: r for r in sectors.board("industries", "1D", _ctx())["rows"]}
    assert themes["SMH"]["leader_why"] == cmb.MARKET_NO_MEMBER_FILE_WHY


def test_seven_days_ranks_the_biggest_names_by_their_closes():
    closes = {"LLY": [["2026-10-0" + str(d), 100.0] for d in range(1, 10)] + [["2026-10-12", 104.0]],
              "JNJ": [["2026-10-0" + str(d), 100.0] for d in range(1, 10)] + [["2026-10-12", 98.0]]}
    got = sectors.top("movers", "7D", _ctx(closes=lambda s: closes.get(s)), None)
    xlv = next(c for c in got["cards"] if c["etf"] == "XLV")
    assert [r["symbol"] for r in xlv["rows"]] == ["LLY", "JNJ"]
    assert xlv["rows"][0]["change_pct"] == 4.0 and xlv["rows"][0]["spark"]


def test_cards_show_before_the_etfs_are_quoted():
    got = sectors.top("movers", "1D", _ctx(etf={}, pool={"LLY": _q(101.0)}), None)
    assert len(got["cards"]) == cmb.MARKET_TOP_CARDS
    assert any(r["symbol"] == "LLY" for c in got["cards"] for r in c["rows"])


def test_no_holdings_file_says_so():
    ctx = _ctx()
    ctx["holdings"] = lambda etf: None
    assert sectors.top("biggest", "1D", ctx, None)["why"] == "State Street's holdings files have not been read"


def test_runners_show_a_card_per_theme_up_to_every_sector_count():
    runners = [(f"Theme {i}", [{"symbol": f"R{i}", "last": 2.0, "change_pct": 50.0}]) for i in range(14)]
    got = sectors.top("runners", "7D", _ctx(), runners)
    assert len(got["cards"]) == cmb.MARKET_TOP_CARDS and got["cards"][0]["rows"][0]["symbol"] == "R0"


# -- the board -----------------------------------------------------------------------------------------------------

def test_the_board_is_not_loading_once_the_climate_answered_in_this_process(monkeypatch):
    monkeypatch.setattr(board.climate, "compose", lambda period, now: None)
    monkeypatch.setattr(board.climate, "today_numbers", lambda now: {})
    monkeypatch.setattr(board.climate, "runners_by_theme", lambda period, now: [])
    st = Store()
    now = clock.at(DAY, 17 * 60 + 38)
    params = {"sectors": "1D", "industries": "1D", "climate": "1D", "top": "movers", "top_period": "1D"}
    assert board.compose(st, now, enabled=True, replay_desk=False, params=params)["loading"] is True
    st.fail("climate", "leaderboard", "no store", now)
    assert board.compose(st, now, enabled=True, replay_desk=False, params=params)["loading"] is False


def test_the_board_after_hours_prices_every_future_and_fills_every_card(monkeypatch):
    monkeypatch.setattr(board.climate, "compose", lambda period, now: None)
    monkeypatch.setattr(board.climate, "today_numbers", lambda now: {})
    monkeypatch.setattr(board.climate, "runners_by_theme", lambda period, now: [])
    st = Store()
    now = clock.at(DAY, 17 * 60 + 38)
    bar = clock.at(DAY, 16 * 60 + 55)
    quotes = {}
    for spec in cmb.MARKET_QUOTES:
        if spec["sec_type"] == "SPREAD":
            continue
        quotes[spec["id"]] = {"id": spec["id"], "last": None, "prev_close": 100.0, "data_type": "live", "at": now}
        st.put(f"line:{spec['id']}", "ibkr", [[clock.at(DAY, 4 * 60), 100.0], [bar, 101.0]], now - 60)
    st.put("quotes", "ibkr", quotes, now - 5)
    st.put("pool_quotes:0", "ibkr", {"LLY": _q(99.0)}, now - 5)
    _put_holdings(st, now, XLV=["LLY"])
    params = {"sectors": "1D", "industries": "1D", "climate": "1D", "top": "movers", "top_period": "1D"}
    got = board.compose(st, now, enabled=True, replay_desk=False, params=params)
    tiles = {t["id"]: t for t in got["quotes"]}
    for tid in ("es", "nq", "rty", "ym", "cl", "gc"):
        assert tiles[tid]["last"] == 101.0 and tiles[tid]["stale"] is True and tiles[tid]["change_pct"] == 1.0
    assert tiles["small_caps"]["change_pct"] == 0.0
    assert got["day_read"]["checks"][0]["state"] == "green"      # 4 of 4 futures up on the day
    assert len(got["top"]["cards"]) == cmb.MARKET_TOP_CARDS
    xlv = next(c for c in got["top"]["cards"] if c["etf"] == "XLV")
    assert xlv["rows"] == [{"symbol": "LLY", "last": 99.0, "change_pct": -1.0, "spark": None}]


def _put_holdings(st: Store, now: float, **rows: list[str]) -> None:
    for etf, syms in rows.items():
        st.put(f"holdings:{etf}", "ssga", {"rows": [{"symbol": s} for s in syms], "fetched_at": now}, now)
