"""The Market page's readers (ADR 053): State Street's file, NYSE breadth, the climate, the tiles and the route."""
from __future__ import annotations

import io
import sys
import zipfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market_board import board, breadth, climate, clock, holdings, ibkr_reads, industries
from market_board.state import Store

DAY = date(2026, 10, 13)


@pytest.fixture(autouse=True)
def _tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("NOVA_LEADERBOARD_DIR", str(tmp_path / "lb"))
    breadth.reset_for_tests()
    climate.reset_for_tests()
    industries.reset_for_tests()
    yield
    breadth.reset_for_tests()
    climate.reset_for_tests()
    industries.reset_for_tests()


def _xlsx(rows: list[list]) -> bytes:
    strings: list[str] = []

    def cell(ref: str, value) -> str:
        if isinstance(value, (int, float)):
            return f'<c r="{ref}" t="n"><v>{value}</v></c>'
        strings.append(str(value))
        return f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>'

    body = "".join(f'<row r="{i + 1}">' + "".join(cell(f"{chr(65 + j)}{i + 1}", v) for j, v in enumerate(r))
                   + "</row>" for i, r in enumerate(rows))
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    sst = f'<sst {ns}>' + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/sharedStrings.xml", sst)
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData>{body}</sheetData></worksheet>")
    return buf.getvalue()


def test_holdings_parse_reads_the_table_heaviest_first():
    data = _xlsx([
        ["Fund Name:", "State Street Technology Select Sector SPDR ETF"],
        ["Ticker Symbol:", "XLK"],
        ["Holdings:", "As of 12-Oct-2026"],
        [],
        ["Name", "Ticker", "Identifier", "SEDOL", "Weight", "Sector"],
        ["APPLE INC", "AAPL", "037833100", "2046251", 13.8577, "-"],
        ["NVIDIA CORP", "NVDA", "67066G104", "2379504", 15.2522, "-"],
        ["BERKSHIRE HATHAWAY INC CL B", "BRK.B", "084670702", "2073390", 0.5, "-"],
        ["US DOLLAR", "-", "-", "-", 0.02, "-"],
    ])
    got = holdings.parse(data)
    assert got["as_of"] == "2026-10-12"
    assert [r["symbol"] for r in got["rows"]] == ["NVDA", "AAPL", "BRK B"]


def test_holdings_parse_refuses_a_file_without_the_table():
    with pytest.raises(holdings.HoldingsError):
        holdings.parse(_xlsx([["Fund Name:", "x"], ["Name", "Weight"]]))
    with pytest.raises(holdings.HoldingsError):
        holdings.parse(b"not a zip")


def _q(**kw):
    return {"bid": None, "ask": None, "bid_size": None, "last": None, "data_type": "live", "at": 0.0, **kw}


def test_breadth_samples_persist_and_compose():
    t0 = clock.at(DAY, 10 * 60)
    quotes = {"ad": _q(bid=2012.0, ask=838.0, bid_size=120.0, at=t0), "vol": _q(bid=780.0, ask=220.0, at=t0),
              "tick": _q(last=412.0, at=t0), "trin": _q(last=0.74, at=t0)}
    sample = breadth.sample_from(quotes)
    assert sample["advancing"] == 2012.0 and sample["up_volume"] == 780.0 and sample["trin"] == 0.74
    breadth.record(sample, DAY, t0)
    breadth.record({**sample, "advancing": 2100.0, "at": t0 + 60}, DAY, t0 + 60)
    breadth.reset_for_tests()          # a restart: the line comes back from the day's file
    got = breadth.compose(t0 + 61, DAY, "regular", None, None)
    assert got["state"] == "ok" and got["advancing"] == 2100.0
    assert [p[1] for p in got["ad_line"]] == [1174.0, 1262.0]
    next_pre = breadth.compose(clock.at(date(2026, 10, 14), 8 * 60), date(2026, 10, 14), "premarket", None, None)
    assert next_pre["state"] == "waiting" and next_pre["prior"]["date"] == "2026-10-13"
    assert breadth.sample_from({"ad": _q()}) is None


def test_breadth_that_stopped_mid_session_is_unavailable_but_keeps_its_line():
    t0 = clock.at(DAY, 10 * 60)
    sample = breadth.sample_from({"ad": _q(bid=2012.0, ask=838.0, at=t0), "tick": _q(last=412.0, at=t0)})
    breadth.record(sample, DAY, t0)
    later = breadth.compose(clock.at(DAY, 13 * 60), DAY, "regular", None, "waiting for spare market-data lines")
    assert later["state"] == "unavailable" and later["advancing"] is None
    assert later["why"].startswith("no NYSE breadth sample since 10:00 ET") and len(later["ad_line"]) == 1
    after_close = breadth.compose(clock.at(DAY, 17 * 60), DAY, "after_hours", None, None)
    assert after_close["state"] == "ok" and after_close["advancing"] == 2012.0   # the day's last sample


def test_an_old_holdings_file_is_not_used(monkeypatch):
    import time as _time

    from market_board import disk

    disk.write("holdings-XLK.json", {"etf": "XLK", "as_of": "2026-09-01", "fetched_at": _time.time() - 30 * 86400,
                                      "rows": [{"symbol": "NVDA", "name": None, "weight_pct": 15.0}]})
    assert holdings.cached("XLK") is not None
    assert holdings.usable("XLK", _time.time()) is None
    disk.write("holdings-XLK.json", {"etf": "XLK", "as_of": "2026-10-12", "fetched_at": _time.time() - 3600,
                                      "rows": [{"symbol": "NVDA", "name": None, "weight_pct": 15.0}]})
    assert holdings.usable("XLK", _time.time())["as_of"] == "2026-10-12"


def _seed_leaderboard(tmp_path: Path) -> None:
    from leaderboard import store

    db_path = Path(tmp_path / "lb") / "leaderboard.sqlite3"
    with store.connect(db_path) as db:
        for day in clock.sessions_back(DAY, 3):
            iso = day.isoformat()
            m = int(clock.at(day, 9 * 60 + 45))
            db.execute("INSERT INTO coverage VALUES (?,?,?,?,?,?,?)", (iso, m, "recorded", "gainers", "live", 3, "r"))
        rows = [  # (symbol, minute offset from 09:45, price, prev_close, change, gap)
            ("RUNR", 0, 3.00, 1.00, 2.00, 0.50), ("RUNR", 60, 3.10, 1.00, 2.10, 0.50),
            ("GAPX", 0, 1.30, 1.00, 0.30, 0.25), ("GAPX", 60, 1.20, 1.00, 0.20, 0.25),
            ("SMOL", 0, 1.10, 1.00, 0.10, 0.0),
        ]
        iso = DAY.isoformat()
        base = int(clock.at(DAY, 9 * 60 + 45))
        for sym, off, price, prev, chg, gap in rows:
            db.execute("INSERT INTO rows (session_date, minute_ts, source, board, symbol, rank, price, prev_close,"
                       " change_pct, gap_pct) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (iso, base + off * 60, "recorded", "gainers", sym, 1, price, prev, chg, gap))
        db.execute("INSERT INTO halt_events VALUES (?,?,?,?,?,?,?,?)",
                   ("RUNR", base + 120.0, "start", "LUDP", "LUDP", "nasdaq_trade_halt_rss", iso, base + 120.0))
        db.commit()


def test_climate_counts_runners_gappers_and_halts(tmp_path):
    _seed_leaderboard(tmp_path)
    now = clock.at(DAY, 11 * 60)
    runners = climate.refresh(now, sessions_needed=3)
    assert runners == ["GAPX", "RUNR"]
    industries.put_many({"RUNR": {"category": "Biotechnology"}}, now)
    block = climate.compose("1D", now)
    assert block["counts"] == {"up20": 2, "up50": 1, "up100": 1}
    assert block["gappers"]["held"] == 1 and block["gappers"]["total"] == 2   # RUNR held its open, GAPX did not
    assert block["halts"]["count"] == 1 and block["halts"]["by_side"] is None
    assert block["theme"]["name"] == "Biotechnology"
    assert block["top"][0]["symbol"] == "RUNR" and block["top"][0]["change_pct"] == 210.0
    assert block["covered"] == 1   # the two sessions before hold coverage but no runners
    assert climate.today_numbers(now)["runners"] == 2


def _seed_massive(path: Path, day: date) -> None:
    """The day movers index with one session built: a runner, a sub-50-cent one, a warrant and an after-close one."""
    from day_movers import store as movers_store

    iso = day.isoformat()
    t = lambda minute: int(clock.at(day, minute))  # noqa: E731
    base = {"session_date": iso, "prev_date": None, "split_suspect": 0, "open": 1.0, "low": 1.0, "volume": 1e6}
    rows = [
        {**base, "symbol": "MASV", "kind": "CS", "prev_close": 2.0, "pm_high": 3.1, "high": 4.4, "close": 3.0,
         "up20_ts": t(8 * 60), "up50_ts": t(8 * 60 + 30), "up100_ts": t(10 * 60)},
        {**base, "symbol": "PENY", "kind": "CS", "prev_close": 0.30, "pm_high": 0.5, "high": 0.5, "close": 0.4,
         "up20_ts": t(9 * 60)},
        {**base, "symbol": "MASVW", "kind": "WARRANT", "prev_close": 1.0, "pm_high": 2.0, "high": 2.0, "close": 1.5,
         "up20_ts": t(9 * 60)},
        {**base, "symbol": "LATE", "kind": "CS", "prev_close": 5.0, "pm_high": 5.0, "high": 5.2, "close": 5.1,
         "up20_ts": t(17 * 60)},
    ]
    with movers_store.connect(path) as db:
        movers_store.replace_session(db, {"session_date": iso, "tickers": 4, "rows": 4, "minute_bars": 1,
                                         "builder": 1, "built_ts": 0.0}, rows)


def test_a_session_nova_did_not_record_is_filled_from_massive_on_the_chart_only(tmp_path, monkeypatch):
    """The operator, 2026-10-14: "fill out the previous days by using data from Massive"."""
    from day_movers import store as movers_store
    from leaderboard import store

    db_path = Path(tmp_path / "lb") / "leaderboard.sqlite3"
    with store.connect(db_path) as db:   # only today is recorded
        db.execute("INSERT INTO coverage VALUES (?,?,?,?,?,?,?)",
                   (DAY.isoformat(), int(clock.at(DAY, 9 * 60 + 45)), "recorded", "gainers", "live", 0, "r"))
        db.commit()
    two_back, one_back = clock.sessions_back(DAY, 3)[:2]
    mv_path = tmp_path / "movers.sqlite3"
    _seed_massive(mv_path, one_back)                                   # two_back: not built in the index
    monkeypatch.setattr(climate, "_massive_store", lambda: movers_store.read_only(mv_path))
    now = clock.at(DAY, 11 * 60)
    assert climate.refresh(now, sessions_needed=3) == ["MASV"]          # its industry is asked of IBKR
    industries.put_many({"MASV": {"category": "Biotechnology"}}, now)
    block = climate.compose("7D", now)
    days = {d["date"]: d for d in block["days"]}
    assert days[one_back.isoformat()] == {"date": one_back.isoformat(), "source": "massive", "total": 1,
                                         "themes": {"Biotechnology": 1}}
    assert days[two_back.isoformat()]["source"] is None                 # still hatched: never a zero
    assert block["covered"] == 1 and block["counts"]["up20"] == 0       # the counts stay on Nova's own lens
    assert block["baseline"] is None and block["themes"] == [] and block["top"] == []
    assert climate.runners_by_theme("7D", now) == []


def test_a_missing_massive_index_leaves_the_gap_hatched(tmp_path, monkeypatch):
    from leaderboard import store

    with store.connect(Path(tmp_path / "lb") / "leaderboard.sqlite3"):
        pass
    monkeypatch.setattr(climate, "_massive_store", lambda: None)
    now = clock.at(DAY, 11 * 60)
    climate.refresh(now, sessions_needed=2)
    assert all(d["source"] is None for d in climate.compose("1D", now)["days"])


def test_quote_extraction_and_tiles():
    ticker = SimpleNamespace(last=float("nan"), bid=118400.0, ask=118440.0, close=116000.0, bidSize=1.0,
                             askSize=2.0, marketDataType=3)
    q = ibkr_reads._quote(ticker, {"id": "btc", "sec_type": "CRYPTO"}, None, None)
    assert q["last"] == 118420.0 and q["price_basis"] == "mid" and q["data_type"] == "delayed"
    spec_tnx = {"id": "tnx", "label": "10-year yield", "symbol": "TNX", "sec_type": "IND", "exchange": "CBOE"}
    tile = board._tile(spec_tnx, {"last": 41.2, "prev_close": 41.5}, [], DAY, clock.at(DAY, 10 * 60))
    assert tile["last"] == pytest.approx(4.12) and tile["prev_close"] == pytest.approx(4.15)
    es = {"change_pct": 0.62, "prev_close": 100.0, "line": [[0, 100.62]], "data_type": "live", "at": 1}
    rty = {"change_pct": 1.31, "prev_close": 50.0, "line": [[0, 50.655]], "data_type": "live", "at": 1}
    spread = board._spread({"es": es, "rty": rty}, {"id": "small_caps", "label": "x", "symbol": "RTY - ES"})
    assert spread["change_pct"] == pytest.approx(0.69) and spread["line"] == [[0, pytest.approx(0.69)]]


def test_a_tile_without_a_snapshot_reads_its_bars_labelled_and_says_when_stale():
    now = clock.at(DAY, 10 * 60 + 2)
    line = [[clock.at(DAY, 9 * 60 + 55), 6840.0], [clock.at(DAY, 10 * 60), 6842.5]]
    got = board._from_bars(None, line, {"date": "2026-10-12", "close": 6800.25}, now)
    assert got["last"] == 6842.5 and got["prev_close"] == 6800.25 and got["data_type"] == "bars"
    assert got["stale"] is False
    assert board._from_bars({"last": 6843.0}, line, None, now)["last"] == 6843.0        # a snapshot wins
    # An hour-old bar (ADR 053 amendment 2026-10-13 evening): its price with its time, flagged stale -- not "--".
    old = board._from_bars(None, line, None, now + 3600)
    assert old["last"] == 6842.5 and old["stale"] is True and old["at"] == line[-1][0]


def test_board_route_validates_and_answers(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from market_board import routes

    monkeypatch.setenv("NOVA_MARKET_BOARD", "0")
    monkeypatch.setattr(routes, "_replay_desk", lambda: False)
    monkeypatch.setattr(routes, "store", lambda: Store())
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    bad = client.get("/api/market/board?climate=2W")
    assert bad.status_code == 400 and bad.json()["detail"]["field"] == "climate"
    ok = client.get("/api/market/board?sectors=7D&top=biggest")
    body = ok.json()
    assert ok.status_code == 200 and body["schema_version"] == 1 and body["enabled"] is False
    assert [q["id"] for q in body["quotes"]][:4] == ["es", "nq", "rty", "ym"]
    assert body["sectors"]["period"] == "7D" and body["top"]["kind"] == "biggest"
    assert body["climate"] is None and body["day_read"]["verdict"] is None
