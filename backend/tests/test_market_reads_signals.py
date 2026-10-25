"""The signal table (``research/signals/build_signals.py``, ``research/market_reads/signal*.py``) on a tiny fake Massive
folder: the in-play universe is chosen minute by minute (a later bar never chooses a stock earlier), a day cut short
reads the same as the whole day up to the cut (no look-ahead in any signal), a mix of signals enters at its first
minute and is scored like a relative-volume trigger against an in-play control, the conditions come only from the
list, a catalyst counts only once published, and the tape stage reads a flush from prints at the bid."""
from __future__ import annotations

import contextlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

pytest.importorskip("pandas")
pytest.importorskip("duckdb")
REPO = Path(__file__).resolve().parents[2]
for extra in (REPO / "research", REPO / "research" / "rvol", REPO / "research" / "signals",
              Path(__file__).resolve().parent):
    sys.path.insert(0, str(extra))

import build_rvol  # noqa: E402
import build_signals  # noqa: E402
import inputs  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
from test_market_reads_daily import write_gz  # noqa: E402

from market_reads import daily, reads, signal_outcomes, signals, slots, splits, tickers  # noqa: E402
from market_reads import signal_registry as reg  # noqa: E402
from market_reads import signals_store as ss  # noqa: E402

HEADER = "ticker,volume,open,close,high,low,window_start,transactions"


def _sessions(n: int = 24) -> list[str]:
    out, d = [], date(2026, 8, 3)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


DAYS = _sessions()
TODAY = DAYS[-1]
SYMBOLS = ("RUN", "CTL", "NOV", "PEN", "SLO")
TICKERS = [{"ticker": s, "cik": str(n), "name": s, "active": True, "type": "CS"} for n, s in enumerate(SYMBOLS, 1)]


def _today(symbol: str) -> list[tuple]:
    """(time, open, high, low, close, volume) on TODAY."""
    if symbol == "RUN":         # in play at 07:00 (+20%, 60,000 shares), then +25% over 2.40 at 10:00
        steady = [(f"07:{m:02d}", 2.4, 2.42, 2.38, 2.4, 2000) for m in range(1, 59)]
        return [("06:00", 2.0, 2.0, 2.0, 2.0, 500), ("07:00", 2.0, 2.45, 2.0, 2.4, 60_000), *steady,
                ("10:00", 2.4, 3.05, 2.4, 3.0, 5000), ("12:00", 3.0, 3.0, 3.0, 3.0, 300)]
    if symbol == "CTL":         # in play at 06:30 (+15%), flat after
        return [("06:30", 2.0, 2.3, 2.0, 2.3, 60_000), ("08:00", 2.3, 2.3, 2.3, 2.3, 1000),
                ("12:00", 2.3, 2.3, 2.3, 2.3, 300)]
    if symbol == "NOV":         # +25% but only 40,000 shares: never in play
        return [("07:00", 2.0, 2.5, 2.0, 2.5, 40_000)]
    if symbol == "PEN":         # a $0.50 stock: under the universe's price
        return [("07:00", 0.5, 0.8, 0.5, 0.75, 100_000)]
    if symbol == "SLO":         # +12% only at 11:00
        return [("08:00", 2.0, 2.0, 2.0, 2.0, 100), ("11:00", 2.0, 2.25, 2.0, 2.24, 70_000)]
    return []


def bars_for(symbol: str, i: int) -> list[tuple]:
    price = 0.5 if symbol == "PEN" else 2.0
    if DAYS[i] == TODAY:
        return _today(symbol)
    return [(t, price, price, price, price, v) for t, v in (("04:30", 10), ("08:00", 100), ("09:29", 1000),
                                                            ("12:00", 300))]


def write_folder(root: Path, cut: str | None = None) -> None:
    for i, day in enumerate(DAYS):
        minute, day_rows = [], []
        for symbol in SYMBOLS:
            bars = [b for b in bars_for(symbol, i) if cut is None or day != TODAY or b[0] < cut]
            if not bars:
                continue
            minute += [f"{symbol},{v},{o},{c},{h},{lo},{reads._ns(day, t)},1" for t, o, h, lo, c, v in bars]
            day_rows.append(f"{symbol},{sum(b[5] for b in bars)},{bars[0][1]},{bars[-1][4]},"
                            f"{max(b[2] for b in bars)},{min(b[3] for b in bars)},{reads._ns(day, '00:00')},1")
        write_gz(root, "minute_aggs_v1", day, HEADER, minute)
        write_gz(root, "day_aggs_v1", day, HEADER, sorted(day_rows))
    ref = root / "store" / "reference"
    ref.mkdir(parents=True, exist_ok=True)
    (ref / "tickers.json").write_text(json.dumps(TICKERS), encoding="utf-8")
    from day_movers import store
    with store.connect() as db:
        for i, day in enumerate(DAYS):
            db.execute("INSERT INTO sessions VALUES (?, ?, 0, 0, 0, 1, ?, NULL)",
                       (day, DAYS[i - 1] if i else None, 1000.0 + i))
        db.commit()


def patch(mp, base: Path) -> None:
    mp.setenv("NOVA_MARKET_DATA_DIR", str(base / "massive"))
    mp.setenv("NOVA_RVOL_DIR", str(base / "rvol"))
    mp.setenv("NOVA_SIGNALS_DIR", str(base / "signals"))
    mp.setattr(slots, "heavy", lambda what, wait=0: contextlib.nullcontext())
    # The desk's own stores, fixed: whatever another test left in the shared folders never changes these rows.
    mp.setattr(inputs, "read_catalysts", lambda day, symbols: {s: ([], []) for s in symbols})
    mp.setattr(inputs, "read_boards", lambda day, symbols: ({}, [], None))
    mp.setattr(inputs, "read_halts", lambda day, built: ([], []))       # the log read, no halt that day
    mp.setattr(inputs, "read_floats", lambda day, symbols: {})
    mp.setattr(inputs, "read_hod", lambda day, symbols: None)
    mp.setattr(splits, "_all", lambda: (pd.DataFrame(columns=["ticker", "execution_date", "split_from", "split_to",
                                                              "source", "price_factor"]), "test"))
    tickers.clear()
    daily.clear()


def _build(base: Path, cut: str | None = None) -> None:
    with pytest.MonkeyPatch.context() as mp:
        patch(mp, base)
        write_folder(base / "massive", cut)
        build_rvol.build(say=lambda *_: None, polite=False)
        build_signals.build(start=DAYS[20], workers=1, say=lambda *_: None, polite=False)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    base = tmp_path_factory.mktemp("signals")
    _build(base)
    cut = tmp_path_factory.mktemp("signals_cut")
    _build(cut, cut="08:00")
    return base, cut


@pytest.fixture
def table(built, monkeypatch):
    patch(monkeypatch, built[0])
    yield built[0]
    tickers.clear()
    daily.clear()


def _minutes(base: Path, day: str = TODAY) -> pd.DataFrame:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("NOVA_SIGNALS_DIR", str(base / "signals"))
        return pq.read_table(ss.minutes_path(day)).to_pandas()


def test_universe_is_chosen_minute_by_minute(table):
    days = pq.read_table(ss.days_path(TODAY)).to_pandas().set_index("symbol")
    assert days.loc["RUN", "in_play_m"] == 7 * 60
    assert days.loc["CTL", "in_play_m"] == 6 * 60 + 30
    assert days.loc["SLO", "in_play_m"] == 11 * 60
    assert "NOV" not in days.index and "PEN" not in days.index      # too few shares; under $1
    rows = _minutes(table)
    assert rows[rows["symbol"] == "SLO"]["m"].min() == 11 * 60       # no row before it was in play
    assert rows[rows["symbol"] == "RUN"]["m"].max() == ss.LAST_M


def test_a_day_cut_short_reads_the_same_up_to_the_cut(built):
    """Every signal at a minute is what the data up to that minute says: the day cut at 08:00 is the same day."""
    whole, cut = _minutes(built[0]), _minutes(built[1])
    columns = ["symbol", "m", *reg.MINUTE_COLUMNS]
    a = whole[whole["m"] < 8 * 60][columns].sort_values(["symbol", "m"]).reset_index(drop=True)
    b = cut[cut["m"] < 8 * 60][columns].sort_values(["symbol", "m"]).reset_index(drop=True)
    assert len(a) and set(a["symbol"]) == {"RUN", "CTL"}
    pd.testing.assert_frame_equal(a, b, check_dtype=False)


def test_rows_hold_the_desk_states(table):
    rows = _minutes(table)
    run = rows[rows["symbol"] == "RUN"].set_index("m")
    assert run.loc[420, "price"] == 2.4 and abs(run.loc[420, "change_pct"] - 20.0) < 1e-9
    assert run.loc[420, "catalyst"] == "not_checked"                 # no source looked: unknown, never no news
    assert run.loc[420, "halted"] == False and run.loc[420, "halts"] == "No halts"   # noqa: E712 -- numpy bool
    assert run.loc[420, "board_state"] == "unknown" and run.loc[420, "hod_today"] == "unknown"
    for column in reg.MINUTE_COLUMNS:
        s = reg.BY_COLUMN[column]
        if s.kind in ("state", "label"):
            seen = set(rows[column].dropna())
            assert seen <= set(s.values), (column, seen - set(s.values))
    assert set(rows["setup_first_pullback"]) <= set(reg.LANE_STATES)


def test_signal_test_enters_first_minute_and_scores_against_an_in_play_control(table):
    answer = signal_outcomes.test(when=[{"signal": "change_pct", "min": 15}],
                                  filters={"date_from": TODAY, "date_to": TODAY}, window_from="07:00",
                                  window_to="10:00", up_pct=20, down_pct=20, group_by="none", seed=3)
    assert answer["entries"] == 1
    s = answer["summary"][0]
    assert s["up"] == 1                                              # 2.40 -> 3.05 at 10:00
    c = answer["control"][0]
    assert c["entries"] == 1 and c["neither"] == 1                   # CTL: in play by 07:00, never +15%


def test_fresh_leaves_out_what_held_before_the_window(table):
    base = {"when": [{"signal": "change_pct", "min": 10}], "filters": {"date_from": TODAY, "date_to": TODAY},
            "window_from": "07:00", "window_to": "10:00", "group_by": "none", "control": False}
    assert signal_outcomes.test(**base)["entries"] == 2                         # RUN at 07:00, CTL at the open
    fresh = signal_outcomes.test(**base, fresh=True)
    assert fresh["entries"] == 1 and fresh["meta"]["left_out"]["held_before_window"] == 1


def test_series_and_scan(table):
    frame = signals.series("RUN", TODAY, ["price", "change_pct", "tape"])
    assert frame["time_et"].iloc[0] == "07:00" and frame["in_play_et"].iloc[0] == "07:00"
    assert set(frame["tape"]) == {"not_built"}
    window = signals.series("RUN", TODAY, ["price"], start="07:30", end="07:35")
    assert window["time_et"].tolist() == ["07:30", "07:31", "07:32", "07:33", "07:34"]
    at = signals.scan(TODAY, "07:30", [{"signal": "change_pct", "min": 15}])
    assert at["symbol"].tolist() == ["RUN"]
    with pytest.raises(LookupError, match="tape stage"):
        signals.scan(TODAY, "07:30", [{"signal": "tape", "is": "flush"}])
    assert {"tape", "tape_score", "tape_flush", "tape_burst"} <= set(at.columns)     # the same shape on any day
    assert set(at["tape"]) == {"not_built"}


def test_conditions_come_only_from_the_list():
    with pytest.raises(ValueError, match="unknown signal"):
        reg.check([{"signal": "x; DROP TABLE", "is": "ok"}])
    with pytest.raises(ValueError, match="one of"):
        reg.check([{"signal": "front", "is": "Sideways"}])
    with pytest.raises(ValueError, match="number"):
        reg.check([{"signal": "pillars_n", "is": 4}])
    with pytest.raises(ValueError, match="true or false"):
        reg.check([{"signal": "halted", "is": "no"}])
    with pytest.raises(ValueError, match="not a tape reading"):
        reg.check([{"signal": "tape", "is": "not_built"}])
    assert reg.check([{"signal": "front", "is": ["Front side", "Mixed"]}]) == [
        {"signal": "front", "is": ["Front side", "Mixed"]}]


def test_a_catalyst_counts_only_once_published():
    import evaluate
    from inputs import ts_of
    item = {"title": "Acme announces FDA approval of its drug", "source": "edgar", "publisher": "x",
            "n_tickers": 1, "form": "8-K", "sec_items": "8.01", "url": "u", "published_ts": ts_of(TODAY, 8 * 60)}
    cat = evaluate.Catalyst(TODAY, [item], ["edgar"])
    assert cat.at(ts_of(TODAY, 7 * 60 + 59))["verdict"] == "none_found"
    assert cat.at(ts_of(TODAY, 8 * 60 + 1))["verdict"] != "none_found"


def test_tape_stage_reads_a_flush_from_prints_at_the_bid(monkeypatch):
    import tape
    from inputs import ts_of

    def ns(m: int, s: float) -> int:
        return int((ts_of(TODAY, m) + s) * 1e9)
    quotes = pd.DataFrame({"sip_timestamp": [ns(415, 0)], "bid_price": [2.0], "ask_price": [2.02],
                           "bid_size": [500.0], "ask_size": [500.0]})
    sells = [ns(420, 1 + i * 0.5) for i in range(12)]
    trades = pd.DataFrame({"sip_timestamp": sells, "price": [2.0] * 12, "size": [500.0] * 12,
                           "exchange": [11] * 12, "correction": [0] * 12, "sets_price": [True] * 12,
                           "conditions": [None] * 12})
    monkeypatch.setattr(reads, "trades", lambda *a, **k: trades)
    monkeypatch.setattr(reads, "quotes", lambda *a, **k: quotes)
    got = tape.stock_day(TODAY, "RUN", 419)
    by = dict(zip(got["m"], zip(got["tape"], got["tape_flush"], strict=True), strict=True))
    assert by[420][1] is True                                        # sold at the bid inside 07:00
    assert by[419][1] is False


def test_status_names_the_table(table):
    st = ss.status()
    assert st["days"] == 4 and st["first"] == DAYS[20] and st["last"] == TODAY


def test_manifest_writers_never_drop_each_others_days(tmp_path, monkeypatch):
    """The minute and tape stages may finish days at once: every update survives (the manifest lock)."""
    import threading
    monkeypatch.setenv("NOVA_SIGNALS_DIR", str(tmp_path / "signals"))

    def writer(key: str) -> None:
        for i in range(25):
            ss.update_manifest(lambda data, i=i: data.setdefault(key, {}).__setitem__(f"2026-01-{i + 1:02d}", {}))
    threads = [threading.Thread(target=writer, args=(k,)) for k in ("days", "tape")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    data = ss.load_manifest()
    assert len(data["days"]) == 25 and len(data["tape"]) == 25
    assert not (tmp_path / "signals" / "manifest.lock").exists()


def test_a_windows_pending_delete_lock_is_waited_for_not_raised(tmp_path, monkeypatch):
    """#1221: on Windows, creating a lock file that is still pending delete (or replacing / deleting a file another
    handle holds) is PermissionError. It killed a writer thread under load and lost its remaining days."""
    monkeypatch.setenv("NOVA_SIGNALS_DIR", str(tmp_path / "signals"))
    real_open, real_replace, real_unlink = ss.os.open, ss.os.replace, Path.unlink
    refusals = {"open": 2, "replace": 2, "unlink": 2}

    def refuse(kind, real):
        def call(*args, **kwargs):
            if refusals[kind]:
                refusals[kind] -= 1
                raise PermissionError(13, "Access is denied")
            return real(*args, **kwargs)
        return call

    monkeypatch.setattr(ss.os, "open", refuse("open", real_open))
    monkeypatch.setattr(ss.os, "replace", refuse("replace", real_replace))
    monkeypatch.setattr(Path, "unlink", refuse("unlink", real_unlink))
    ss.update_manifest(lambda data: data["days"].__setitem__("2026-01-02", {}))
    assert refusals == {"open": 0, "replace": 0, "unlink": 0}
    assert "2026-01-02" in ss.load_manifest()["days"]
    assert not (tmp_path / "signals" / "manifest.lock").exists()


def test_a_lasting_refusal_still_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SIGNALS_DIR", str(tmp_path / "signals"))
    monkeypatch.setattr(ss, "SHARING_RETRY_SEC", 0.05)

    def never(*_a, **_k):
        raise PermissionError(13, "Access is denied")
    monkeypatch.setattr(ss.os, "replace", never)
    with pytest.raises(PermissionError):
        ss.update_manifest(lambda data: None)
    assert not (tmp_path / "signals" / "manifest.lock").exists()


def test_catalyst_category_and_reason_confidence_are_signals(table):
    rows = _minutes(table)
    for column in ("catalyst_category", "catalyst_strength", "why_confidence"):
        assert column in rows.columns and column in {s["signal"] for s in reg.catalog()}
    assert reg.check([{"signal": "catalyst_category", "is": "contract"}]) == [
        {"signal": "catalyst_category", "is": ["contract"]}]
    with pytest.raises(ValueError, match="one of"):
        reg.check([{"signal": "catalyst_strength", "is": "huge"}])


def test_the_cli_refuses_a_yes_or_no_it_cannot_read():
    sys.path.insert(0, str(REPO / "tools"))
    import market_data_signals as cli
    assert cli.conditions(["halted=false"]) == [{"signal": "halted", "is": False}]
    with pytest.raises(SystemExit, match="true or false"):
        cli.conditions(["halted=yes"])


def test_a_halt_carried_from_the_day_before_is_halted_until_it_resumes():
    import evaluate
    from inputs import ts_of
    prior = [{"symbol": "RUN", "ts": ts_of(DAYS[-2], 19 * 60 + 50), "event": "start", "kind": "T1", "code": "T1",
              "source": "nasdaq"}]
    today = [{"symbol": "RUN", "ts": ts_of(TODAY, 9 * 60 + 35), "event": "end", "kind": "T1", "code": "T1",
              "source": "nasdaq"}]
    assert evaluate._halts(today, prior, "RUN", ts_of(TODAY, 9 * 60), TODAY)[1] is True     # before the resume
    assert evaluate._halts(today, prior, "RUN", ts_of(TODAY, 9 * 60 + 40), TODAY)[1] is False
    assert evaluate._halts([], prior, "RUN", ts_of(TODAY, 9 * 60), TODAY)[1] is True


def test_share_counts_are_filed_the_day_before_on_the_days_split_basis(monkeypatch):
    from day_movers import floats
    from day_movers import store as dm_store
    seen = {}

    class Db:
        def close(self):
            pass
    monkeypatch.setattr(dm_store, "read_only", lambda: Db())
    monkeypatch.setattr(floats, "sec_shares", lambda db, pairs, before=False: seen.update(pairs=pairs, before=before)
                        or {(TODAY, "RUN"): {"shares": 5_000_000}})
    assert inputs.read_floats(TODAY, ["RUN"]) == {"RUN": {"shares": 5_000_000}}
    assert seen == {"pairs": [(TODAY, "RUN")], "before": True}
