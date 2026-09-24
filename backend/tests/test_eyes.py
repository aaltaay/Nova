"""The eyes on the record (ADR 029): the journal of everything the lanes see, the
same lanes run over a Session Record, the Sim eyes following the playhead, and
backtests of templates -- none of it ever in setups.db or the live read-out."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from eyes import backtest, journal, reader
from eyes.recording import Recording, _sample_books, _ticks, load
from eyes.replay import EyesReplay
from eyes.sim_eyes import HISTORICAL_NOTE, SimEyes
from setup_templates.store import TemplateStore, default_template, set_store_for_tests
from tests.setup_scanner_fixtures import add, base_morning, leg_up

ET = ZoneInfo("America/New_York")
SYM = "ABCD"
DAY = "2026-09-21"
PILLARS = {"price": 4.35, "change_pct": 40.0, "rvol": 8.0, "float": 5_000_000.0, "news": None, "headline": None,
           "catalyst": None}


def _pillars(sym, date, ts, *, last_price, prev_close):
    return dict(PILLARS)


def bars():
    return add(leg_up(base_morning(), [4.08, 4.18, 4.28, 4.38]), 4.38, 4.37, 4.30, 4.32, 30_000)


def recording(*, record_from: float | None = None) -> Recording:
    """The fixture morning: armed at the pullback bar's close, near at 4.35 with green tape, a trigger at 4.38,
    then the target. Prints and books exist only from ``record_from`` on."""
    b = bars()
    armed_at = b[-1].t + 60
    start = armed_at if record_from is None else record_from
    prints, books = [], []
    for i in range(0, 120):
        ts = armed_at + i * 0.5
        if ts < start:
            continue
        books.append({"ts": ts, "bids": [{"price": 4.34, "size": 4000}], "asks": [{"price": 4.37, "size": 3000}]})
        if i % 2:
            continue
        price = 4.35 if i < 20 else (4.38 if i < 40 else 4.56)
        prints.append({"ts": ts, "price": price, "size": 100, "side": "ask", "exchange": "NSDQ", "conditions": ""})
    prints.append({"ts": armed_at + 5.2, "price": 9.99, "size": 5, "side": "ask", "exchange": "NSDQ",
                   "conditions": "I"})           # an odd lot: tape, never a price
    prints.sort(key=lambda r: r["ts"])
    sampled = _sample_books(books, 0.5)
    return Recording(date=DAY, symbol=SYM, prints=prints, print_ts=[p["ts"] for p in prints],
                     ticks=_ticks(prints, 1.0), books=sampled, book_ts=[t for t, _ in sampled], bars=b,
                     bars_source="archive", spans=[(start, armed_at + 60)] if prints else [], prev_close=3.0)


# -- the journal ---------------------------------------------------------------------------
def test_the_journal_writes_one_line_per_observation_by_eastern_day(monkeypatch, tmp_path):
    monkeypatch.setenv("NOVA_EYES_JOURNAL", "1")
    monkeypatch.setenv("NOVA_EYES_DIR", str(tmp_path))
    journal.reset_for_tests()
    journal.record({"event": "armed", "symbol": SYM, "ts": 1.0, "metrics": {"x": float("nan")}})
    assert journal.flush()
    day = datetime.now(ET).strftime("%Y-%m-%d")
    lines = (tmp_path / "journal" / f"{day}.jsonl").read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[0])
    assert row["schema_version"] == 1 and row["event"] == "armed" and row["metrics"]["x"] is None
    assert row["wall_ts"] > 0 and journal.status()["written"] == 1
    monkeypatch.setenv("NOVA_EYES_JOURNAL", "0")
    journal.record({"event": "armed"})
    assert journal.status()["queued"] == 0 and journal.status()["enabled"] is False


def test_the_reader_folds_lines_into_setups_and_skips_unknown_schemas(tmp_path):
    path = tmp_path / "2026-09-21.jsonl"
    rows = [
        {"schema_version": 1, "event": "armed", "source": "live", "template": "default", "setup_id": "S1",
         "symbol": SYM, "ts": 1, "setup": {"trigger": 4.37}, "grade": "B"},
        {"schema_version": 1, "event": "tape", "source": "live", "template": "default", "setup_id": "S1",
         "symbol": SYM, "ts": 2, "verdict": "go"},
        {"schema_version": 1, "event": "triggered", "source": "live", "template": "default", "setup_id": "S1",
         "symbol": SYM, "ts": 3, "tape": {"verdict": "go"}, "setup": {"entry": 4.38}},
        {"schema_version": 1, "event": "scored", "source": "live", "template": "default", "setup_id": "S1",
         "symbol": SYM, "ts": 4, "outcome": "target_first", "bar_r": 1.2},
        {"schema_version": 7, "event": "armed", "setup_id": "S2"},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n", encoding="utf-8")
    skipped: dict[str, int] = {}
    got = reader.setups(reader.lines(path, skipped=skipped))
    assert len(got) == 1 and got[0]["trigger_tape"] == "go" and got[0]["bar_r"] == 1.2 and got[0]["grade"] == "B"
    assert skipped == {"unknown_schema": 1, "unreadable": 1}
    counts = reader.counts(reader.lines(path, event="tape,armed"))
    assert counts["live:default"]["events"] == {"armed": 1, "tape": 1}
    assert reader.days(tmp_path)[0]["date"] == "2026-09-21"


# -- the replay ------------------------------------------------------------------------------
def test_a_replay_arms_reads_the_recorded_tape_triggers_and_scores():
    events: list[dict] = []
    rep = EyesReplay(recording(), [default_template("first_pullback")], source="backtest", all_propose=True,
                     journal=events.append, pillars=_pillars)
    rep.run_to_end()
    [row] = rep.rows.values()
    assert row["trigger"] == 4.37 and row["stop"] == 4.30 and row["template_id"] == "default"
    # Near is read the first second price comes within reach: one print at the ask is not green yet.
    assert row["near_tape"]["verdict"] == "wait" and row["trigger_tape"]["verdict"] == "go"
    assert row["outcome"] == "target_first" and row["triggered_at"]
    kinds = [e["event"] for e in events]
    assert kinds.index("armed") < kinds.index("near") < kinds.index("triggered")
    assert any(e["event"] == "proposal" and e["status"] == "proposed" for e in events)
    assert all(e["source"] == "backtest" and e["replay"] == {"date": DAY, "symbol": SYM} for e in events)
    assert rep.take_alerts() and rep.take_alerts() == []


def test_outside_the_recording_nothing_is_near_and_nothing_triggers():
    b = bars()
    rec = recording(record_from=b[-1].t + 60 + 45)      # the recorder starts after the trigger moment
    rep = EyesReplay(rec, [default_template("first_pullback")], source="backtest", pillars=_pillars)
    rep.run_to_end()
    [row] = rep.rows.values()
    assert row.get("near_at") is None or row["near_tape"]["verdict"] in ("go", "wait", "veto", "blind")
    # the first recorded price is 4.56, far over the trigger: the setup is skipped as a gap-over, never filled
    assert row.get("triggered_at") is None


def test_load_reads_a_session_record_off_disk(tmp_path, monkeypatch):
    rec = recording()
    folder = tmp_path / DAY / SYM
    folder.mkdir(parents=True)
    (folder / "prints.jsonl").write_text("".join(json.dumps({**p, "symbol": SYM}) + "\n" for p in rec.prints),
                                         encoding="utf-8")
    books = [{"ts": t, "symbol": SYM, **b} for t, b in rec.books]
    (folder / "l2.jsonl").write_text("".join(json.dumps(r) + "\n" for r in books), encoding="utf-8")
    got = load(DAY, SYM, root=tmp_path, bars_fn=lambda sym, date: bars())
    assert got.bars_source == "archive" and len(got.bars) == len(bars())
    assert len(got.prints) == len(rec.prints) and all(hi < 9 for _, hi, _ in got.ticks)   # odd lot never a price
    with pytest.raises(ValueError):
        load("2026-09-22", SYM, root=tmp_path)
    # No archive bars: minute bars come from the prints that set a price, never the stored buckets (#535).
    (folder / "bars_1m.jsonl").write_text(json.dumps({"ts": rec.bars[-1].t + 60, "open": 1, "high": 99, "low": 0.5,
                                                      "close": 1, "symbol": SYM}) + "\n", encoding="utf-8")
    own = load(DAY, SYM, root=tmp_path, bars_fn=lambda sym, date: [])
    assert own.bars_source == "recording" and own.bars and max(b.h for b in own.bars) < 9


# -- the Sim eyes -------------------------------------------------------------------------------
def test_sim_eyes_follow_the_playhead_and_journal_each_moment_once(tmp_path):
    set_store_for_tests(TemplateStore(tmp_path / "t.json"))
    rec = recording()
    events: list[dict] = []
    target = {"kind": "capture", "date": DAY, "symbol": SYM, "playhead": rec.bars[-1].t + 30}
    eyes = SimEyes(target=lambda: dict(target), load=lambda d, s: rec, journal=events.append, threaded=False)
    eyes.tick(0)
    board = eyes.board(0)
    assert board["source"] == "sim" and board["replay"]["symbol"] == SYM and board["rows"][0]["state"] == "leg"
    target["playhead"] = rec.bars[-1].t + 60 + 5
    eyes.tick(0)
    board = eyes.board(0)
    assert board["rows"][0]["state"] == "near" and board["template"]["id"] == "default"
    assert board["proposals"] and eyes.take_alerts()
    seen = len(events)
    target["playhead"] = rec.bars[-1].t + 30             # rewind: rebuilt silently
    eyes.tick(0)
    target["playhead"] = rec.bars[-1].t + 60 + 5
    eyes._last_rebuild = 0
    eyes.tick(0)
    assert len(events) == seen                          # nothing journalled twice
    target.update(kind="historical")
    eyes.tick(0)
    hist = eyes.board(0)
    assert hist["rows"] == [] and hist["replay"]["note"] == HISTORICAL_NOTE and hist["proposing"] is False


def test_the_live_board_stays_when_the_desk_is_not_on_a_replay():
    eyes = SimEyes(target=lambda: None, threaded=False)
    eyes.tick(0)
    assert eyes.board(0) is None


# -- backtests --------------------------------------------------------------------------------------
def test_a_backtest_run_keeps_every_setup_and_a_summary_per_template(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_EYES_DIR", str(tmp_path))
    store = TemplateStore(tmp_path / "t.json")
    set_store_for_tests(store)
    wide = store.create("first_pullback", name="Wide", values={"stop_cap": 0.5})

    def fake_load(date, symbol):
        if symbol == "NOPE":
            raise ValueError("NOPE 2026-09-21 holds no usable prints")
        return recording()

    man = backtest.run(sessions=[(DAY, SYM), (DAY, "NOPE")], load=fake_load, run_id="20260921-100000-abcdef")
    assert man["status"] == "done" and [s["status"] for s in man["sessions"]] == ["ok", "skipped"]
    folder = tmp_path / "backtests" / man["run_id"]
    setups = [json.loads(x) for x in (folder / "setups.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {s["template_id"] for s in setups} == {"default", wide.id}
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))["templates"]
    assert summary["default"]["summary"]["all"]["triggered"] == 1
    assert summary["default"]["readout"]["state"] == "collecting"
    assert backtest.list_runs()[0]["run_id"] == man["run_id"]
    events = (folder / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert events and json.loads(events[0])["run_id"] == man["run_id"]


def test_eyes_routes(tmp_path, monkeypatch):
    from eyes import routes

    monkeypatch.setenv("NOVA_EYES_DIR", str(tmp_path))
    set_store_for_tests(TemplateStore(tmp_path / "t.json"))
    started = []
    monkeypatch.setattr(backtest, "start", lambda **kw: started.append(kw) or {"run_id": "x", "status": "running"})
    app = FastAPI()
    app.include_router(routes.router)
    c = TestClient(app)
    assert c.get("/api/eyes/journal").json()["days"] == []
    assert c.post("/api/eyes/backtests", json={"sessions": [{"date": "bad", "symbol": SYM}]}).status_code == 400
    assert c.post("/api/eyes/backtests", json={"sessions": [{"date": DAY, "symbol": "abcd"}]}).status_code == 202
    assert started[-1]["sessions"] == [(DAY, "ABCD")]
    assert c.get("/api/eyes/backtests/../../etc").status_code == 404
    assert c.get("/api/eyes/backtests/20260921-100000-abcdef").status_code == 404
    assert c.get("/api/eyes/backtests").json()["runs"] == []


def test_the_engine_board_defers_to_the_sim_eyes_off_the_live_edge(tmp_path):
    from setup_scanner.engine import SetupEngine

    class Sim:
        def tick(self, now):
            pass

        def board(self, now):
            return {"source": "sim", "rows": []}

        def take_alerts(self):
            return []

    eng = SetupEngine(templates=lambda: TemplateStore(tmp_path / "t.json"), journal=lambda e: None,
                      universe=lambda: [], sim_eyes=lambda: Sim(), bot_state=dict)
    assert eng.board(0)["source"] == "sim"


def test_the_eyes_package_never_imports_an_order_path():
    import ast

    import eyes

    banned = ("execution", "ibkr.orders", "ibkr.order_build", "practice", "bot.actions", "bot.flatten",
              "bot.proposals", "bot.loops")
    for path in sorted(Path(eyes.__file__).parent.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [node.module] if isinstance(node, ast.ImportFrom) and node.module else (
                [a.name for a in node.names] if isinstance(node, ast.Import) else [])
            for name in names:
                assert not any(name == b or name.startswith(b + ".") for b in banned), (path.name, name)
