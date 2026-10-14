"""A rebuilt day's Gappers by the second (ADR 023 amendment 2026-10-13).

A small day in Massive's own file format and a rebuilt leaderboard day: the list at a second is the minute board
priced by the trades before that second -- never one after it -- and every stock that can qualify inside a minute
is on it, including one the store never held.
"""
from __future__ import annotations

import gzip
import json
import sqlite3
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from constants_leaderboard import (
    LEADERBOARD_BOARD_GAPPERS,
    LEADERBOARD_BOARD_MARKET,
    LEADERBOARD_SECONDS_SCHEMA_VERSION,
    LEADERBOARD_SOURCE_RECONSTRUCTED,
    LEADERBOARD_SOURCE_RECORDED,
    LEADERBOARD_STATE_FROZEN,
    LEADERBOARD_STATE_REBUILT,
)
from ibkr.gapper_view import row_qualifies
from leaderboard import routes, store as board_store
from leaderboard.rows import make_row
from leaderboard.seconds import build, inputs, job, playback, run, store
from sim import massive_daily, massive_days

ET = ZoneInfo("America/New_York")
DAY, PRIOR, OTHER = "2026-09-18", "2026-09-17", "2026-09-16"
TRADES = "ticker,conditions,correction,exchange,id,participant_timestamp,price,sequence_number,sip_timestamp,size,tape,trf_id,trf_timestamp"
MINUTES = "ticker,volume,open,close,high,low,window_start,transactions"


def ts(hms: str, day: str = DAY) -> int:
    return int(datetime.fromisoformat(f"{day}T{hms}").replace(tzinfo=ET).timestamp())


def _trade(ticker, hms, ms, price, size, *, seq, conds="", corr=0):
    ns = ts(hms) * 10**9 + ms * 10**6
    conds = f'"{conds}"' if "," in conds else conds
    return f"{ticker},{conds},{corr},12,{seq},{ns},{price},{seq},{ns},{size},3,0,0"


def _bar(ticker, hms, close, high, volume, day=DAY):
    return f"{ticker},{volume},{close},{close},{high},{close},{ts(hms, day) * 10**9},1"


def _write(root, dataset, day, header, lines):
    path = root / dataset / day[:4] / day[5:7] / f"{day}.csv.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="") as fh:
        fh.write(header + "\n" + "\n".join(lines) + "\n")


# AAA: on the board at 07:45 (1.15, +15%), off at 07:45:02 (1.08), back at 07:45:31 (1.20).
# BBB: off at 07:45 (2.10), on at 07:45:11 (2.30), off at 07:45:41 (2.12); after 09:30 runs past AAA.
# CCC: the store never held it; a 1-for-10 split makes its prior close 1.00; on 07:45:21-07:45:50 only.
# WWW: a warrant -- never a gapper, however far it runs.
DAY_TRADES = [
    _trade("AAA", "07:44:30", 0, 1.15, 1000, seq=1),
    _trade("AAA", "07:45:01", 300, 1.08, 1000, seq=2),
    _trade("AAA", "07:45:30", 0, 1.20, 2000, seq=3),
    _trade("AAA", "07:45:30", 0, 1.30, 10, seq=4, conds="37"),          # an odd lot: volume, never the price
    _trade("AAA", "09:29:10", 0, 1.22, 100, seq=5),
    _trade("AAA", "09:30:05", 0, 1.25, 200, seq=6),
    _trade("BBB", "07:44:20", 0, 2.10, 500, seq=1),
    _trade("BBB", "07:45:10", 500, 2.30, 300, seq=2),
    _trade("BBB", "07:45:40", 0, 2.12, 400, seq=3),
    _trade("BBB", "09:29:30", 0, 2.40, 100, seq=4),
    _trade("BBB", "09:30:10", 0, 2.44, 100, seq=5),                      # one nanosecond, two prints:
    _trade("BBB", "09:30:10", 0, 2.70, 200, seq=6),                      # the later sequence number is the last
    _trade("CCC", "07:45:20", 0, 1.50, 400, seq=1),
    _trade("CCC", "07:45:50", 0, 1.05, 100, seq=2),
    _trade("CCC", "07:45:55", 0, 9.99, 100, seq=3, corr=10),             # a cancel record: no trade
    _trade("WWW", "07:45:05", 0, 5.00, 100, seq=1),
]
DAY_BARS = [
    _bar("AAA", "07:44:00", 1.15, 1.16, 1000), _bar("AAA", "07:45:00", 1.20, 1.20, 3000),
    _bar("AAA", "09:29:00", 1.22, 1.22, 100), _bar("AAA", "09:30:00", 1.25, 1.25, 200),
    _bar("BBB", "07:44:00", 2.10, 2.10, 500), _bar("BBB", "07:45:00", 2.12, 2.30, 700),
    _bar("BBB", "09:29:00", 2.40, 2.40, 100), _bar("BBB", "09:30:00", 2.70, 2.70, 300),
    _bar("CCC", "07:45:00", 1.05, 1.50, 400),
    _bar("WWW", "07:45:00", 5.00, 5.00, 100),
]


def _row(symbol, hms, board, rank, price, prev, volume, **extra):
    return {**make_row(symbol=symbol, minute_ts=ts(hms), board=board, source=LEADERBOARD_SOURCE_RECONSTRUCTED,
                       rank=rank, price=price, prev_close=prev, volume=volume, **extra), "session_date": DAY}


def _stored_day(*, extra_rows=()):
    gappers = LEADERBOARD_BOARD_GAPPERS
    rows = [
        _row("AAA", "07:45", gappers, 1, 1.15, 1.00, 1000, has_news=False, exchange="NASDAQ"),
        _row("AAA", "07:46", gappers, 1, 1.20, 1.00, 4010, has_news=True,
             news_first_seen_ts=ts("07:45:40"), exchange="NASDAQ"),
        _row("AAA", "07:45", LEADERBOARD_BOARD_MARKET, 3, 1.15, 1.00, 1000, exchange="NASDAQ"),
        _row("BBB", "07:45", LEADERBOARD_BOARD_MARKET, 9, 2.10, 2.00, 500, rvol=3.0, rvol_basis="time_of_day_20",
             exchange="NYSE", float_shares=5e6),
        _row("BBB", "07:46", LEADERBOARD_BOARD_MARKET, 9, 2.12, 2.00, 1200, exchange="NYSE", float_shares=5e6),
        _row("AAA", "09:30", gappers, 1, 1.22, 1.00, 4110),
        _row("BBB", "09:30", gappers, 2, 2.40, 2.00, 1300),
        *extra_rows,
    ]
    coverage = [{"session_date": DAY, "minute_ts": ts("07:45"), "source": LEADERBOARD_SOURCE_RECONSTRUCTED,
                 "board": gappers, "state": LEADERBOARD_STATE_REBUILT, "row_count": 1, "run_id": None}]
    with board_store.connect() as db:
        board_store.write_batch(db, rows=rows, coverage=coverage)


@pytest.fixture
def day(tmp_path, monkeypatch):
    root = tmp_path / "massive"
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(root))
    monkeypatch.setattr(job, "launch", job._launch_thread)
    massive_daily.reset_for_tests()
    massive_days.reset_for_tests()
    _write(root, "trades_v1", DAY, TRADES, DAY_TRADES)
    _write(root, "minute_aggs_v1", DAY, MINUTES, DAY_BARS)
    _write(root, "minute_aggs_v1", PRIOR, MINUTES, [_bar("AAA", "15:59:00", 1.00, 1.00, 1, PRIOR)])
    _write(root, "day_aggs_v1", PRIOR, MINUTES, [_bar(t, "09:30:00", c, c, 1, PRIOR) for t, c in
                                                 (("AAA", 1.0), ("BBB", 2.0), ("CCC", 0.10), ("WWW", 1.0))])
    reference = root / "store" / "reference"
    reference.mkdir(parents=True)
    (reference / "tickers.json").write_text(json.dumps([
        {"ticker": "AAA", "type": "CS"}, {"ticker": "BBB", "type": "CS"},
        {"ticker": "CCC", "type": "ADRC"}, {"ticker": "WWW", "type": "WARRANT"}]), encoding="utf-8")
    (reference / "splits.json").write_text(json.dumps([
        {"ticker": "CCC", "execution_date": DAY, "split_from": 10, "split_to": 1}]), encoding="utf-8")
    _stored_day()
    yield root
    job.reset_for_tests()
    massive_daily.reset_for_tests()


def _wait(day_=DAY, until=("ready", "failed", "stopped"), timeout=30.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        state = job.status(day_)
        if state.get("status") in until:
            return state
        time.sleep(0.05)
    raise AssertionError(f"build of {day_} still {job.status(day_)}")


def _built():
    job.request(DAY)
    return _wait()


def _symbols(hms):
    return [(row["symbol"], row["price"]) for row in playback.answer(DAY, ts(hms))["rows"]]


# ── The pure core ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("price, prev", [(1.10, 1.00), (1.0999, 1.00), (0.55, 0.50), (0.50, 0.40), (0.4999, 0.40),
                                         (2.20, 2.00), (11.0, 10.0)])
def test_the_rule_is_the_live_gappers_rule(price, prev):
    change = (price - prev) / prev
    assert build.qualifies(price, prev) == row_qualifies({"symbol": "X", "price": price, "prev_close": prev,
                                                          "change_pct": change})


def test_a_bar_counts_only_from_its_close():
    bars = [(ts("07:44:00"), 1.2, 1.1, 10.0), (ts("07:45:00"), 1.5, 1.3, 20.0)]
    got = list(build.as_of(bars, [ts("07:44"), ts("07:45"), ts("07:46")]))
    assert got[0][1:3] == (None, 0.0) and got[0][3] == bars[0]
    assert got[1][1:3] == (1.1, 10.0) and got[1][3] == bars[1]
    assert got[2][1:3] == (1.3, 30.0) and got[2][3] is None


def test_a_stock_is_a_candidate_only_in_minutes_it_can_qualify():
    bars = [(ts("07:44:00"), 1.05, 1.05, 1.0), (ts("07:45:00"), 1.30, 1.04, 1.0)]
    found = build.premarket_candidates("X", bars, 1.00, [ts("07:44"), ts("07:45"), ts("07:46")])
    assert [c.minute for c in found] == [ts("07:45")]            # only the bar with a high over the floor
    assert build.premarket_candidates("X", bars, 2.00, [ts("07:45")]) == []


def test_the_last_print_of_a_second_is_the_latest_sip_time_then_sequence():
    ns = ts("09:30:10") * 10**9
    prints = [(ns, 6, 2.70, 200.0, True), (ns, 5, 2.44, 100.0, True), (ns + 5, 7, 2.80, 10.0, False),
              (ts("09:31:00") * 10**9, 8, 3.0, 1.0, True)]
    assert build.tally_seconds(prints, [ts("09:30")]) == [(ts("09:30:10"), 2.70, 310.0)]


def test_a_print_is_seen_only_from_the_next_second():
    candidate = build.Candidate(ts("07:45"), "AAA", 1.15, 1000.0, 1.00)
    seconds = {"AAA": [(ts("07:45:01"), 1.08, 1000.0)]}
    assert build.list_at(ts("07:45:01"), [candidate], seconds)[0]["price"] == 1.15
    assert build.list_at(ts("07:45:02"), [candidate], seconds) == []        # +8%: off the list


# ── A build, read back ──────────────────────────────────────────────────────

def test_the_list_moves_second_by_second_and_never_reads_ahead(day):
    state = _built()
    assert state["status"] == "ready", state
    summary = state["summary"]
    assert summary["from_outside_store"] == 1                              # CCC
    assert summary["checked_minutes"] == summary["agreed_minutes"] == 2    # 07:45 and 07:46 as stored
    assert summary["read_indexed"] == summary["stocks_read"] == 3          # never WWW
    assert _symbols("07:45:00") == [("AAA", 1.15)]                          # the stored minute board
    assert _symbols("07:45:01") == [("AAA", 1.15)]
    assert _symbols("07:45:02") == []
    assert _symbols("07:45:11") == [("BBB", 2.30)]
    assert _symbols("07:45:21") == [("CCC", 1.50), ("BBB", 2.30)]
    assert _symbols("07:45:31") == [("CCC", 1.50), ("AAA", 1.20), ("BBB", 2.30)]
    assert _symbols("07:45:41") == [("CCC", 1.50), ("AAA", 1.20)]
    assert _symbols("07:45:56") == [("AAA", 1.20)]                          # the cancel record moved nothing


def test_a_row_carries_the_minutes_other_columns(day):
    _built()
    rows = {row["symbol"]: row for row in playback.answer(DAY, ts("07:45:41"))["rows"]}
    aaa, ccc = rows["AAA"], rows["CCC"]
    assert aaa["volume"] == 1000 + 1000 + 2000 + 10                         # the odd lot counts in the volume
    assert aaa["change_pct"] == pytest.approx(0.20) and aaa["gap_pct"] == aaa["change_pct"]
    assert aaa["has_news"] is True and aaa["news_first_seen_ts"] == ts("07:45:40")
    assert aaa["minute_ts"] == ts("07:45") and aaa["second_ts"] == ts("07:45:41") and aaa["rank"] == 2
    assert ccc["prev_close"] == pytest.approx(1.00)                         # 0.10 before the 1-for-10 split
    assert ccc["exchange"] is None and ccc["rvol"] is None and ccc["halted"] is None
    bbb = {row["symbol"]: row for row in playback.answer(DAY, ts("07:45:11"))["rows"]}["BBB"]
    assert (bbb["rvol"], bbb["exchange"], bbb["float_shares"]) == (3.0, "NYSE", 5e6)
    assert playback.answer(DAY, ts("07:45:01"))["rows"][0]["has_news"] is False


def test_a_stock_new_to_the_list_takes_the_days_facts_from_the_next_minute(day):
    _stored_day(extra_rows=[_row("CCC", "07:46", LEADERBOARD_BOARD_MARKET, 40, 1.05, 1.00, 500, exchange="NYSE",
                                 float_shares=2e6, rvol=9.0, rvol_basis="time_of_day_20")])
    _built()
    ccc = {row["symbol"]: row for row in playback.answer(DAY, ts("07:45:21"))["rows"]}["CCC"]
    assert (ccc["exchange"], ccc["float_shares"], ccc["rvol"]) == ("NYSE", 2e6, None)


def test_from_0930_the_frozen_list_keeps_its_order_and_reprices(day):
    _built()
    at_open = playback.answer(DAY, ts("09:30:00"))
    assert at_open["state"] == LEADERBOARD_STATE_FROZEN
    assert _symbols("09:30:00") == [("AAA", 1.22), ("BBB", 2.40)]
    assert _symbols("09:30:11") == [("AAA", 1.25), ("BBB", 2.70)]          # BBB ran past AAA: the order stays
    assert playback.answer(DAY, ts("07:45:00"))["state"] == LEADERBOARD_STATE_REBUILT


def test_no_rows_outside_the_rebuilt_minutes(day):
    _built()
    for hms in ("04:00:30", "20:01:00"):
        answer = playback.answer(DAY, ts(hms))
        assert answer["status"] == "ready" and answer["rows"] == [] and answer["second_ts"] is None


# ── Asking, and what the desk is told ───────────────────────────────────────

def test_before_any_request_the_day_reads_none(day):
    answer = playback.answer(DAY, ts("07:45:00"))
    assert answer["status"] == "none" and answer["rows"] == []


@pytest.mark.parametrize("case, reason", [
    ("recorded", job.RECORDED),
    ("not_rebuilt", job.NOT_REBUILT),
    ("no_trades", "The day's Massive trades file is not on disk"),
])
def test_a_day_that_cannot_be_built_says_why(day, case, reason):
    target = DAY
    if case == "recorded":
        with board_store.connect() as db:
            board_store.write_batch(db, coverage=[{"session_date": DAY, "minute_ts": ts("07:45"),
                                                   "source": LEADERBOARD_SOURCE_RECORDED, "board": "gainers",
                                                   "state": "live", "row_count": 0, "run_id": "r"}])
    elif case == "not_rebuilt":
        target = OTHER
        _write(day, "minute_aggs_v1", OTHER, MINUTES, [])
        _write(day, "trades_v1", OTHER, TRADES, [])
    else:
        (day / "trades_v1" / DAY[:4] / DAY[5:7] / f"{DAY}.csv.gz").unlink()
    assert job.request(target) == {"status": "unavailable", "reason": reason}


def test_a_ready_day_is_not_built_again_until_its_rebuild_changes(day, monkeypatch):
    _built()
    started = []
    monkeypatch.setattr(job, "launch", lambda d: started.append(d) or job._launch_thread(d))
    assert job.request(DAY)["status"] == "ready" and started == []
    with board_store.connect() as db:                                      # the day is rebuilt: another price
        db.execute("UPDATE rows SET price = 1.16 WHERE symbol = 'AAA' AND board = 'gappers' AND minute_ts = ?",
                   (ts("07:45"),))
        db.commit()
    assert job.request(DAY)["status"] == "queued" and started == [DAY]
    assert _wait()["status"] == "ready"


def test_asking_for_another_day_stops_the_running_build(day, monkeypatch):
    def slow(day_, stop=None):
        store.write_job(day_, "gappers", status="building", stage="trades")
        stop.wait(10)
        raise inputs.Cancelled()

    monkeypatch.setattr(run, "run", slow)
    job.request(DAY)
    _wait(until=("building",))
    _write(day, "minute_aggs_v1", OTHER, MINUTES, [])
    _write(day, "trades_v1", OTHER, TRADES, [])
    with board_store.connect() as db:
        board_store.write_batch(db, rows=[{**_row("AAA", "07:45", "gappers", 1, 1.15, 1.0, 1), "session_date": OTHER,
                                           "minute_ts": ts("07:45", OTHER)}])
    job.request(OTHER)
    assert _wait(DAY)["status"] == "stopped"


def test_a_build_that_fails_says_why(day, monkeypatch):
    def broken(day_, stop=None):
        raise OSError("the disk went away")

    monkeypatch.setattr(run, "run", broken)
    job.request(DAY)
    state = _wait()
    assert state["status"] == "failed" and state["error"] == "the disk went away"


def test_a_build_no_process_rewrites_reads_failed_and_a_fresh_one_is_never_doubled(day, monkeypatch):
    class Done:
        def alive(self):
            return False

    store.write_job(DAY, "gappers", status="building", stage="trades")
    started = []
    monkeypatch.setattr(job, "launch", lambda d: started.append(d) or Done())
    assert job.request(DAY)["status"] == "building" and started == []       # an earlier backend's build, still alive
    path = store.job_path(DAY, "gappers")
    old = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**old, "updated_ts": time.time() - 3600}), encoding="utf-8")
    assert job.status(DAY)["status"] == "failed"
    job.request(DAY)
    assert started == [DAY]


def test_files_of_an_unknown_version_are_never_read(day):
    _built()
    path = store.job_path(DAY, "gappers")
    path.write_text(json.dumps({**json.loads(path.read_text(encoding="utf-8")), "schema_version": 99}), encoding="utf-8")
    assert job.status(DAY) == {"status": "none"}
    store.write_job(DAY, "gappers", status="ready")
    db = sqlite3.connect(store.data_path(DAY, "gappers"))
    db.execute("PRAGMA user_version = 99")
    db.commit()
    db.close()
    assert store.open_data(DAY, "gappers") is None
    assert playback.answer(DAY, ts("07:45:00"))["status"] == "none"


def test_a_build_that_stops_leaves_no_file(day, monkeypatch):
    def interrupted(*_a, **_k):
        raise inputs.Cancelled()

    monkeypatch.setattr(build, "tally_seconds", interrupted)
    with pytest.raises(inputs.Cancelled):
        run.run(DAY)
    assert not store.data_path(DAY, "gappers").exists()
    assert not list(store.folder().glob("*.part"))


def test_the_routes(day):
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    assert client.post(f"/api/leaderboard/{DAY}/seconds").json()["status"] in ("queued", "building", "ready")
    _wait()
    body = client.get(f"/api/leaderboard/{DAY}/seconds", params={"at": ts("07:45:31") + 0.6}).json()
    assert body["schema_version"] == LEADERBOARD_SECONDS_SCHEMA_VERSION and body["board"] == "gappers"
    assert body["second_ts"] == ts("07:45:31") and [r["symbol"] for r in body["rows"]] == ["CCC", "AAA", "BBB"]
    assert client.get("/api/leaderboard/2026-13-01/seconds", params={"at": 1}).status_code == 400


def test_the_desk_builds_in_its_own_process(monkeypatch):
    monkeypatch.setattr("sys.frozen", True, raising=False)
    assert job.worker_command(DAY)[1:] == ["--board-seconds", "--date", DAY]
    monkeypatch.setattr("sys.frozen", False, raising=False)
    assert job.worker_command(DAY)[1:] == ["-m", "leaderboard.seconds.worker", "--date", DAY]


def test_the_worker_runs_one_build(day, monkeypatch):
    from leaderboard.seconds import worker

    monkeypatch.setenv("NOVA_BOARD_SECONDS_MEMORY_MB", "0")
    assert worker.main(["--board-seconds", "--date", DAY]) == 0
    assert store.read_job(DAY, "gappers")["status"] == "ready"


def test_a_real_build_process_finishes_the_day(day, monkeypatch):
    monkeypatch.setattr(job, "launch", job._launch_process)
    monkeypatch.setenv("NOVA_BOARD_SECONDS_MEMORY_MB", "0")
    job.request(DAY)
    state = _wait(timeout=120.0)
    assert state["status"] == "ready", state
    assert _symbols("07:45:31") == [("CCC", 1.50), ("AAA", 1.20), ("BBB", 2.30)]
