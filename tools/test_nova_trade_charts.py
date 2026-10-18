"""Trade list in, frozen 10-second chart bundle out; generated bars only, no Massive files, no browser."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nova_trade_charts as trades  # noqa: E402
from nova_historical_resolver import HistoricalChartError  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DAY = "2023-05-02"
TRADE = {"symbol": "DEMO", "date": DAY, "entry_time": "07:05:22", "entry_price": 3.39,
         "exits": [{"time": "07:06:01", "price": 3.49}, {"time": "07:10:20", "price": 4.10}],
         "stop": 3.33, "pivot": 3.35, "label": "best 1"}


def expect(code, action):
    with pytest.raises(HistoricalChartError) as caught:
        action()
    assert caught.value.code == code


def test_a_trade_becomes_one_marked_window():
    [plan] = trades.normalize_trades([TRADE])
    assert (plan["symbol"], plan["day"]) == ("DEMO", DAY)
    assert plan["start_s"] == 7 * 3600 + 22 // 10 * 10 + 5 * 60 - 300
    assert plan["end_s"] == 7 * 3600 + 10 * 60 + 20 + 120
    kinds = [(a["kind"], a.get("side"), a.get("second"), a["price"]) for a in plan["annotations"]]
    assert kinds[:3] == [("trade_marker", "buy", 25522.0, 3.39), ("trade_marker", "sell", 25561.0, 3.49),
                         ("trade_marker", "sell", 25820.0, 4.10)]
    lines = {a["label"]: (a["price"], a["color"]) for a in plan["annotations"] if a["kind"] == "horizontal_line"}
    assert lines == {"Stop 3.33": (3.33, "grey"), "Pivot 3.35": (3.35, "gold")}


def test_flat_exit_fields_and_fractional_seconds():
    flat = {"symbol": "DEMO", "date": DAY, "entry_time": "09:30:00.250", "entry_price": 2,
            "exit_time": "09:30:31", "exit_price": 2.1}
    [plan] = trades.normalize_trades([flat])
    marks = [a for a in plan["annotations"] if a["kind"] == "trade_marker"]
    assert [m["second"] for m in marks] == [34200.25, 34231.0]
    assert [m["side"] for m in marks] == ["buy", "sell"]


def test_two_trades_on_one_stock_day_share_a_chart():
    later = dict(TRADE, entry_time="09:00:00", exits=[{"time": "09:00:30", "price": 3.5}], label="second")
    [plan] = trades.normalize_trades([later, TRADE])
    assert plan["start_s"] == 25522 // 10 * 10 - 300 and plan["end_s"] == 9 * 3600 + 30 + 120
    assert sum(a["kind"] == "trade_marker" for a in plan["annotations"]) == 5


def test_stock_days_sort_by_date_then_symbol():
    plans = trades.normalize_trades([dict(TRADE, symbol="ZZZ"), dict(TRADE, date="2022-01-03"), TRADE])
    assert [(p["day"], p["symbol"]) for p in plans] == [("2022-01-03", "DEMO"), (DAY, "DEMO"), (DAY, "ZZZ")]


@pytest.mark.parametrize("change,code", [
    (dict(exits=[{"time": "07:05:00", "price": 3.4}]), "invalid_trade"),
    (dict(entry_time="7:5"), "invalid_trade"),
    (dict(entry_time="25:00:00"), "invalid_trade"),
    (dict(entry_price=0), "invalid_trade"),
    (dict(stop=float("nan")), "invalid_trade"),
    (dict(symbol="../X"), "invalid_symbol"),
    (dict(extra=1), "invalid_trade"),
])
def test_bad_trades_refuse(change, code):
    expect(code, lambda: trades.normalize_trades([dict(TRADE, **change)]))


def test_more_than_nine_stock_days_refuse():
    many = [dict(TRADE, symbol=f"S{i}") for i in range(10)]
    expect("invalid_entries", lambda: trades.normalize_trades(many))


@pytest.mark.parametrize("seconds", [0, 7, 60, True])
def test_bar_size_is_sub_minute_on_the_supported_grid(seconds):
    expect("invalid_bar_seconds", lambda: trades.normalize_trades([TRADE], bar_seconds=seconds))


def frame(rows):
    times = pd.to_datetime([f"{DAY} {t}" for t, *_ in rows]).tz_localize("America/New_York")
    return pd.DataFrame({"time_et": times, "open": [r[1] for r in rows], "high": [r[2] for r in rows],
                         "low": [r[3] for r in rows], "close": [r[4] for r in rows], "volume": [r[5] for r in rows],
                         "transactions": [1] * len(rows)})


def test_projection_trims_the_window_and_keeps_volume_only_buckets_as_gaps():
    rows = [("07:00:00", 3.0, 3.1, 2.9, 3.0, 100), ("07:00:10", float("nan"), float("nan"), float("nan"),
            float("nan"), 50), ("07:00:20", 3.0, 3.2, 3.0, 3.1, 70), ("07:05:00", 3.1, 3.1, 3.1, 3.1, 1)]
    bars, dropped = trades.project_bars(frame(rows), 25200, 25230, 10)
    assert [b["s"] for b in bars] == [25200, 25220]
    assert bars[1] == {"s": 25220, "o": 3.0, "h": 3.2, "l": 3.0, "c": 3.1, "v": 70.0}
    assert dropped == 1


def massive_root(tmp_path):
    root = tmp_path / "massive"
    (root / "trades_v1").mkdir(parents=True)
    return root


def test_bundle_is_frozen_and_accepted_by_the_native_gallery(tmp_path):
    calls = []

    def read(symbol, day, tf, start, end):
        calls.append((symbol, day, tf, start, end))
        return frame([("07:00:00", 3.3, 3.4, 3.3, 3.35, 100), ("07:00:20", 3.3, 3.4, 3.3, 3.35, 100),
                      ("07:05:20", 3.35, 3.4, 3.35, 3.39, 900),
                      ("07:10:20", 3.9, 4.1, 3.9, 4.1, 500)])

    output = tmp_path / "out"
    receipt = trades.resolve_trade_bundle([TRADE], output, massive_root(tmp_path), read=read)
    assert calls == [("DEMO", DAY, "10s", "07:00", "07:13")]
    selection = json.loads(Path(receipt["selection_path"]).read_text(encoding="utf-8"))
    entry = selection["selected"][0]
    assert entry["bar_seconds"] == 10 and "as_of_m" not in entry
    projection = json.loads((output / "bars" / "01.json").read_text(encoding="utf-8"))
    assert projection["s_semantics"] == "second_START" and projection["bar_seconds"] == 10
    assert receipt["sources"][0]["reader"] == "market_reads.bars"
    assert "sha256" not in receipt["sources"][0]
    sys.path.insert(0, str(REPO / "backend"))
    from agent_desk.chart_gallery import load_gallery
    wire = load_gallery(Path(receipt["selection_path"]), receipt["selection_sha256"])
    assert len(wire["entries"][0]["bars_sub"]) == 3


def test_a_root_without_trades_refuses_before_claiming_output(tmp_path):
    output = tmp_path / "out"
    expect("trades_root_missing", lambda: trades.resolve_trade_bundle(
        [TRADE], output, tmp_path, read=lambda *a: frame([])))
    assert not output.exists()


def test_a_stock_day_with_no_priced_bars_refuses(tmp_path):
    output = tmp_path / "out"
    expect("symbol_missing", lambda: trades.resolve_trade_bundle(
        [TRADE], output, massive_root(tmp_path), read=lambda *a: frame([])))
    assert not output.exists()
