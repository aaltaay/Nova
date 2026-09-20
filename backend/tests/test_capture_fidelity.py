"""Capture fidelity stays observable through writes, restart and compatibility read."""
import json
from datetime import datetime
from pathlib import Path

import pytest

from capture import bar_buckets, bridge_sim, recorder, sessions
from capture.constants_capture import CAPTURE_SCHEMA_VERSION
from sim import capture_player as player, session_clock

DAY = "2026-09-18"
TS = datetime.fromisoformat(DAY + "T10:00:00-04:00").timestamp()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SIM_CAPTURE_DIR", str(tmp_path))
    recorder.reset_for_tests()
    bar_buckets.reset_for_tests()
    player.reset_for_tests()
    session_clock.reset_for_tests()
    session_clock.set_session_date(DAY)
    yield tmp_path
    recorder.reset_for_tests()
    bar_buckets.reset_for_tests()
    player.reset_for_tests()
    session_clock.reset_for_tests()


def rows(directory, name):
    return [json.loads(line) for line in (directory / (name + ".jsonl")).read_text().splitlines()]


def start():
    recorder.start_recorder("SIM1")
    return Path(recorder.status()["dir"])


def test_l2_event_time_keeps_final_quiet_book_and_counts_coalescing():
    directory = start()
    for ts, price in [(TS, 10), (TS + .01, 11), (TS + .02, 12), (TS + .13, 13), (TS + .14, 14)]:
        recorder.record_l2(dict(symbol="SIM1", ts=ts, bids=[dict(price=price, size=1)], asks=[]))
    recorder.stop_recorder()
    recorded = rows(directory, "l2")
    assert [row["bids"][0]["price"] for row in recorded] == [10, 13, 14]
    assert all(row["schema_version"] == CAPTURE_SCHEMA_VERSION for row in recorded)
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["schema_version"] == CAPTURE_SCHEMA_VERSION
    assert manifest["fidelity"]["l2_offered"] == 5
    assert manifest["fidelity"]["l2_coalesced"] == 2


def test_backward_scrub_stops_before_duplicate_print_or_bar():
    directory = start()
    bridge_sim._write_sim_tick(dict(time=TS, price=10, size=3), None, None)
    bridge_sim._write_sim_tick(dict(time=TS - 1800, price=20, size=30), None, None)
    assert not recorder.is_recording()
    assert "backwards" in recorder.status()["error"]
    assert recorder.status()["fidelity"]["timestamp_regressions"] == 1
    assert [row["price"] for row in rows(directory, "prints")] == [10]
    assert rows(directory, "bars_1m")[0]["volume"] == 3


def test_resume_keeps_timestamp_high_water_mark():
    directory = start()
    recorder.record_print(dict(ts=TS + 10, symbol="SIM1", price=10))
    recorder.stop_recorder()
    recorder.start_recorder("SIM1")
    assert not recorder.record_print(dict(ts=TS, symbol="SIM1", price=11))
    assert len(rows(directory, "prints")) == 1
    assert "backwards" in recorder.last_error()


@pytest.mark.parametrize("ts", [None, -1, float("nan"), float("inf"), True, 1e30])
def test_invalid_write_timestamp_fails_loudly(ts):
    directory = start()
    assert not recorder.record_print(dict(ts=ts, symbol="SIM1", price=10))
    assert recorder.status()["fidelity"]["invalid_timestamp_rows"] == 1
    assert "timestamp" in recorder.last_error()
    assert rows(directory, "prints") == []


def test_bad_sim_time_cannot_substitute_wall_clock():
    with pytest.raises(ValueError, match="refusing wall-clock"):
        bridge_sim._unix("not a date")


def test_sim_calendar_rollover_uses_new_event_directory():
    directory = start()
    bridge_sim._write_sim_tick(dict(time=TS, price=10, size=1), None, None)
    next_ts = datetime.fromisoformat("2026-09-21T04:00:00-04:00").timestamp()
    bridge_sim._write_sim_tick(dict(time=next_ts, price=11, size=1), None, None)
    new_directory = Path(recorder.status()["dir"])
    recorder.stop_recorder()
    assert directory.parent.name == DAY
    assert new_directory.parent.name == "2026-09-21"
    assert [row["price"] for row in rows(directory, "prints")] == [10]
    assert [row["price"] for row in rows(new_directory, "prints")] == [11]
    assert len(rows(directory, "bars_1d")) == len(rows(new_directory, "bars_1d")) == 1


def test_daily_bar_emits_once_for_3600_prints():
    directory = start()
    for offset in range(3600):
        bar_buckets.on_print("SIM1", TS + offset, 10, 2, source="sim", session_date=DAY)
    assert rows(directory, "bars_1d") == []
    recorder.stop_recorder()
    daily = rows(directory, "bars_1d")
    assert len(daily) == 1
    assert daily[0]["volume"] == 7200


@pytest.mark.parametrize("iso", ["2026-09-18T04:30:00-04:00", "2026-11-01T01:30:00-04:00", "2026-11-01T01:30:00-05:00"])
def test_daily_anchor_never_follows_input_even_across_dst(iso):
    ts = datetime.fromisoformat(iso).timestamp()
    assert bar_buckets._day_open_ts(ts) <= ts


def fixture_capture(root, manifest=None):
    directory = root / DAY / "SIM1"
    directory.mkdir(parents=True)
    (directory / "prints.jsonl").write_text(json.dumps(dict(ts=TS, symbol="SIM1", price=10)) + "\n")
    if manifest is not None:
        (directory / "manifest.json").write_text(json.dumps(manifest))
    return directory


@pytest.mark.parametrize("version", [2, "1", True, 1.5])
def test_unknown_manifest_version_refuses_load_and_listing(isolated, version):
    fixture_capture(isolated, {"schema_version": version})
    loaded = player.load(DAY, "SIM1")
    assert not loaded["ok"] and "schema_version" in loaded["error"]
    entry = sessions.list_sessions()["tickers_by_day"][DAY][0]
    assert not entry["usable"] and "schema_version" in entry["unavailable_reason"]


def test_corrupt_manifest_visible_even_with_valid_prints(isolated):
    directory = fixture_capture(isolated)
    (directory / "manifest.json").write_text("{torn")
    assert not player.load(DAY, "SIM1")["ok"]
    assert "malformed" in sessions.list_sessions()["tickers_by_day"][DAY][0]["unavailable_reason"]


def test_unknown_row_version_refuses_load(isolated):
    directory = fixture_capture(isolated, {"schema_version": 1})
    (directory / "prints.jsonl").write_text(json.dumps(dict(ts=TS, price=10, schema_version=99)))
    assert "schema_version" in player.load(DAY, "SIM1")["error"]


def test_legacy_migration_counts_all_rejected_rows_and_bounds_l2(isolated, monkeypatch):
    directory = fixture_capture(isolated, {"schema": "sim_capture_v1"})
    with (directory / "prints.jsonl").open("a") as out:
        out.write('null\n{torn\n' + json.dumps(dict(ts=None, price=10)) + "\n")
        out.write(json.dumps(dict(ts=TS, price=0)) + "\n")
    (directory / "l2.jsonl").write_text("".join(json.dumps(dict(ts=TS + i, bids=[], asks=[])) + "\n" for i in range(12)))
    # Unused daily file is intentionally unreadable JSON. It must not be opened.
    (directory / "bars_1d.jsonl").write_text("{unused old duplicate flood")
    monkeypatch.setattr(player, "CAPTURE_L2_LOAD_LIMIT", 4)
    info = player.load(DAY, "SIM1")
    assert info["ok"] and info["legacy_schema"]
    assert info["malformed_rows"] == 2
    assert info["invalid_timestamp_rows"] == 1
    assert info["invalid_rows"] == 1
    assert info["l2_total"] == 12 and info["l2_loaded"] == 4 and info["l2_decimated"]
    assert player.book_at(TS)["ts"] == TS
    assert player.book_at(TS + 11)["ts"] == TS + 11
    # Playback never touches disk once selected, including empty L2.
    monkeypatch.setattr(player, "_read_jsonl", lambda *a: pytest.fail("playback performed disk I/O"))
    assert player.book_at(TS + 11)["ts"] == TS + 11


@pytest.mark.parametrize("bad", [dict(size="many"), dict(size=[]), dict(size=-1), dict(size=float("inf"))])
def test_malformed_print_sizes_are_counted_not_crashed(isolated, bad):
    directory = fixture_capture(isolated)
    with (directory / "prints.jsonl").open("a") as out:
        out.write(json.dumps(dict(ts=TS + 1, price=11, **bad)) + "\n")
    info = player.load(DAY, "SIM1")
    assert info["ok"] and info["invalid_rows"] == 1
    assert len(player.prints_since(TS - 1, TS + 2)) == 1


@pytest.mark.parametrize("levels", [["wrong"], [dict(price=10, size="many")], [dict(price=float("nan"), size=1)]])
def test_malformed_book_levels_are_counted(isolated, levels):
    directory = fixture_capture(isolated)
    (directory / "l2.jsonl").write_text(json.dumps(dict(ts=TS, bids=levels, asks=[])))
    info = player.load(DAY, "SIM1")
    assert info["invalid_rows"] == 1 and info["l2_total"] == 0
    assert player.book_at(TS) is None


def test_resume_refuses_unknown_row_version_in_middle(isolated):
    directory = fixture_capture(isolated, {"schema_version": 1})
    with (directory / "prints.jsonl").open("a") as out:
        out.write(json.dumps(dict(ts=TS + 1, price=11, schema_version=99)) + "\n")
        out.write(json.dumps(dict(ts=TS + 2, price=12, schema_version=1)) + "\n")
    with pytest.raises(ValueError, match="schema_version"):
        recorder.start_recorder("SIM1")
    assert not recorder.is_recording()
    assert len(rows(directory, "prints")) == 3


def test_invalid_bridge_time_records_failure_count():
    start()
    bridge_sim._write_sim_tick(dict(time="bad", price=10, size=1), None, None)
    assert not recorder.is_recording()
    assert recorder.status()["fidelity"]["invalid_timestamp_rows"] == 1


@pytest.mark.parametrize("field", ["bid", "ask", "prev_close", "volume", "bid_size", "ask_size"])
def test_malformed_quote_numbers_cannot_crash_quote_lookup(isolated, field):
    directory = fixture_capture(isolated)
    (directory / "quotes.jsonl").write_text(json.dumps(dict(ts=TS, last=10, **{field: "bad"})))
    info = player.load(DAY, "SIM1")
    assert info["invalid_rows"] == 1
    assert player.quote_at(TS)["last"] == 10



def test_prints_only_capture_never_invents_quotes_depth_or_daily_facts(isolated, monkeypatch):
    from sim import market, replay
    fixture_capture(isolated)
    assert replay.set_replay(DAY, "SIM1")["replay_ok"]
    monkeypatch.setattr(session_clock, "now_et", lambda: datetime.fromtimestamp(TS, session_clock.ET))
    quote = market.quote("SIM1")
    assert quote["last"] == 10
    assert all(quote[key] is None for key in ("bid", "ask", "bid_size", "ask_size", "prev_close"))
    assert market.book() == {}
    ticker = market.ticker_snapshot("SIM1")
    assert ticker["latest_trade"]["price"] == 10 and ticker["latest_trade"]["size"] is None
    assert all(ticker[key] is None for key in ("latest_quote", "daily_bar", "minute_bar", "prev_daily_bar", "prev_close"))
    assert market.quote("OTHER") is None
    assert market.ticker_snapshot("OTHER") == {}


def test_recorded_quotes_preserved_and_no_fallback_before_first_event(isolated, monkeypatch):
    from sim import market, replay
    directory = fixture_capture(isolated)
    recorded = dict(ts=TS, symbol="SIM1", bid=9.9, ask=10.1, last=10,
                    bid_size=25, ask_size=30, prev_close=9.5, volume=100)
    (directory / "quotes.jsonl").write_text(json.dumps(recorded))
    replay.set_replay(DAY, "SIM1")
    monkeypatch.setattr(session_clock, "now_et", lambda: datetime.fromtimestamp(TS, session_clock.ET))
    result = market.quote("SIM1")
    assert all(result[key] == value for key, value in recorded.items())
    projected = market.ticker_snapshot("SIM1")["latest_quote"]
    assert projected["bid"] == projected["bid_price"] == 9.9
    assert projected["ask"] == projected["ask_price"] == 10.1
    assert projected["bid_size"] == 25 and projected["ask_size"] == 30
    monkeypatch.setattr(session_clock, "now_et", lambda: datetime.fromtimestamp(TS - 1, session_clock.ET))
    assert market.quote("SIM1") is None and market.book() == {}
    assert market.ticker_snapshot("SIM1") == {}


def test_failed_capture_stays_unknown_until_explicit_synthetic_selection():
    from sim import market, replay
    replay.set_replay(DAY, "MISSING")
    assert market.quote("SIM1") is None and market.book() == {}
    assert market.ticker_snapshot("SIM1") == {}
    replay.set_replay(None, None)
    quote = market.quote("SIM1")
    assert quote["bid"] < quote["ask"]
    assert market.book()["bids"] and market.ticker_snapshot("SIM1")["daily_bar"]



def test_print_recorded_bbo_projects_canonical_quote_with_unknown_sizes(isolated, monkeypatch):
    from sim import market, replay
    directory = fixture_capture(isolated)
    (directory / "prints.jsonl").write_text(json.dumps(dict(ts=TS, symbol="SIM1", price=10, bid=9.9, ask=10.1)))
    replay.set_replay(DAY, "SIM1")
    monkeypatch.setattr(session_clock, "now_et", lambda: datetime.fromtimestamp(TS, session_clock.ET))
    quote = market.ticker_snapshot("SIM1")["latest_quote"]
    assert quote["bid_price"] == 9.9 and quote["ask_price"] == 10.1
    assert quote["bid_size"] is None and quote["ask_size"] is None
