"""The live eyes' journal played back at a past moment (operator ask, 2026-09-24):
the lanes write every change of a card, the fold draws the card as it stood, a
silence after a beat is a gap, and the Sim desk pops a recorded proposal up only
when the playhead plays across it."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from constants_bot import BOT_SCANNER_SETUPS
from eyes import journal
from eyes.journal_day import JournalDay
from eyes.playback import Playback, board_at, gap_note
from eyes.replay import EyesReplay
from eyes.sim_eyes import SimEyes
from setup_scanner.board import board_body
from setup_templates.store import TemplateStore, default_template, set_store_for_tests
from tests.test_eyes import DAY, SYM, _pillars, recording

LEVELS = {"chosen": "first_pullback", "levels": {"first_pullback": 1}}


def live(event: dict) -> dict:
    """A replay's line as the live engine writes it."""
    out = {k: v for k, v in event.items() if k != "replay"}
    out.update(source="live", date=DAY)
    return out


def header(ts: float) -> list[dict]:
    """What the live engine writes as it starts: the session, its lanes and its names."""
    lanes = [{"setup_type": s, "template": "default", "rev": 1, "name": "Default", "params_hash": "h",
              "playing": True} for s in BOT_SCANNER_SETUPS]
    return [{"event": "session", "symbol": None, "ts": ts, "date": DAY, "source": "live"},
            {"event": "lanes", "symbol": None, "ts": ts, "date": DAY, "source": "live", "lanes": lanes},
            {"event": "watch", "symbol": None, "ts": ts, "date": DAY, "source": "live", "added": [SYM],
             "removed": [], "count": 1}]


def write(path: Path, events: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(journal.line(e) + "\n" for e in events), encoding="utf-8")
    return path


def card(rows: list[dict]) -> dict:
    """What a row must agree on: its state and words, its setup, the tape in reach, its proposal."""
    out = {}
    for r in rows:
        reach = r["state"] in ("armed", "near")
        out[(r["setup_type"], r["symbol"])] = (
            r["state"], r["reason"], r["setup_id"], (r["setup"] or {}).get("trigger"), r["grade"],
            (r["tape"] or {}).get("verdict") if reach else None, (r["proposal"] or {}).get("id"))
    return out


def counts(setups: list[dict]) -> dict:
    return {s["id"]: {k: v for k, v in s["counts"].items() if k != "watching"} for s in setups}


def test_the_journal_played_back_is_the_board_the_lanes_drew_at_every_moment(tmp_path):
    set_store_for_tests(TemplateStore(tmp_path / "t.json"))
    rec = recording()
    lines: list[dict] = []
    rep = EyesReplay(rec, [default_template(s) for s in BOT_SCANNER_SETUPS], source="sim",
                     playing={s: "default" for s in BOT_SCANNER_SETUPS}, journal=lines.append, pillars=_pillars)
    armed_at = rec.bars[-1].t + 60
    moments = sorted({b.t + 60 for b in rec.bars} | {armed_at + i * 0.5 for i in range(0, 130)})
    drawn = []
    for at in moments:
        rep.advance(at)
        body = board_body(rep.playing_lanes(), rep.lanes, LEVELS, rep.now, can_propose=True)
        drawn.append((at, card(body["rows"]), counts(body["setups"])))
    events = header(rec.bars[0].t) + [live(e) for e in lines]
    path = write(tmp_path / f"{DAY}.jsonl", events)

    pb = Playback(JournalDay(path, DAY))
    pb.day.refresh()
    states = set()
    for at, rows, funnel in drawn:
        pb.advance(at)
        body = pb.body(LEVELS)
        assert card(body["rows"]) == rows, at
        assert counts(body["setups"]) == funnel, at
        states |= {r[0] for r in rows.values()}
    # The morning walks the whole ladder, so the check above covered every state a card shows.
    assert {"leg", "armed", "near", "triggered"} <= states
    assert any(e["event"] == "price" for e in lines)          # a name in reach keeps its price on the record


def test_a_line_about_a_symbol_carries_the_detectors_price_and_leg_and_the_trigger_its_words():
    lines: list[dict] = []
    rep = EyesReplay(recording(), [default_template("first_pullback")], source="sim",
                     playing={"first_pullback": "default"}, journal=lines.append, pillars=_pillars)
    rep.run_to_end()
    [trig] = [e for e in lines if e["event"] == "triggered"]
    assert trig["reason"].startswith("traded 4.3") and trig["last"] is not None and trig["leg"]["t"]
    prices = [e["ts"] for e in lines if e["event"] == "price"]
    assert all(b - a >= 5.0 for a, b in zip(prices, prices[1:], strict=False))


def test_a_silence_after_a_beat_is_a_gap_and_the_board_is_not_carried_across_it(tmp_path):
    t = 1_790_250_000.0
    state = {"event": "state", "symbol": SYM, "setup_type": "first_pullback", "template": "default", "rev": 1,
             "playing": True, "state": "leg", "reason": "new high 4.40 on a 10% leg", "ts": t + 5,
             "date": DAY, "source": "live", "leg": {"t": t, "high": 4.4, "low": 4.0, "pct": 0.1}, "last": 4.39}
    beat = {"event": "beat", "symbol": None, "ts": t + 10, "date": DAY, "source": "live", "count": 1}
    restart = header(t + 1000)
    path = write(tmp_path / f"{DAY}.jsonl", header(t) + [state, beat] + restart)
    pb = Playback(JournalDay(path, DAY))
    pb.day.refresh()
    pb.advance(t - 60)
    assert pb.gap()["reason"] == "before_record" and pb.body(LEVELS)["rows"] == []
    pb.advance(t + 60)
    [row] = pb.body(LEVELS)["rows"]
    assert row["state"] == "leg" and row["last_price"] == 4.39
    pb.advance(t + 10 + 181)
    gap = pb.gap()
    assert gap == {"reason": "not_running", "since": t + 10, "until": t + 1000}
    body = pb.body(LEVELS)
    assert body["rows"] == [] and all(not s["recorded"] for s in body["setups"])
    assert "Nothing is carried across the gap" in gap_note(gap, DAY)
    pb.advance(t + 1001)                          # Nova started again: the eyes begin from nothing
    assert pb.gap() is None and pb.body(LEVELS)["rows"] == []


def test_the_day_is_read_as_it_grows_and_only_its_live_lines_count(tmp_path):
    path = tmp_path / f"{DAY}.jsonl"
    day = JournalDay(path, DAY)
    assert day.refresh() == 0 and not day.exists
    t = 1_790_250_000.0
    write(path, header(t) + [{"event": "state", "symbol": SYM, "ts": t + 1, "date": DAY, "source": "sim"},
                             {"event": "state", "symbol": SYM, "ts": t + 1, "date": "2026-09-20",
                              "source": "live"}])
    assert day.refresh() == 3 and day.exists
    with path.open("a", encoding="utf-8") as fh:
        fh.write(journal.line({"event": "beat", "symbol": None, "ts": t + 2, "date": DAY, "source": "live"}) + "\n")
        fh.write('{"schema_version": 1, "event": "be')          # the writer's line, not finished
    assert day.refresh() == 1 and day.lines[-1]["event"] == "beat"
    with path.open("a", encoding="utf-8") as fh:
        fh.write('at", "ts": 1, "date": "%s", "source": "live"}\n{"schema_version": 9}\n' % DAY)
    assert day.refresh() == 1 and day.skipped == 1
    write(path, header(t))                                        # replaced: read again from the start
    gen = day.generation
    day.refresh()
    assert day.generation == gen + 1 and len(day.lines) == 3


def test_the_sim_desk_plays_the_journal_back_and_pops_a_proposal_up_only_when_played_across(tmp_path):
    set_store_for_tests(TemplateStore(tmp_path / "t.json"))
    rec = recording()
    lines: list[dict] = []
    rep = EyesReplay(rec, [default_template(s) for s in BOT_SCANNER_SETUPS], source="sim",
                     playing={s: "default" for s in BOT_SCANNER_SETUPS}, journal=lines.append, pillars=_pillars)
    rep.run_to_end()
    [raised] = [e for e in lines if e["event"] == "proposal" and e["status"] == "proposed"]
    write(tmp_path / "journal" / f"{DAY}.jsonl", header(rec.bars[0].t) + [live(e) for e in lines])
    created = raised["proposal"]["created_at"]
    target = {"kind": "journal", "date": DAY, "playhead": created - 1, "symbol": None, "loaded": None}
    eyes = SimEyes(target=lambda: dict(target), threaded=False, levels=lambda: LEVELS,
                   journal_path=lambda d: tmp_path / "journal" / f"{d}.jsonl")
    eyes.tick(0)
    board = eyes.board(0)
    assert board["source"] == "sim" and board["replay"]["kind"] == "journal" and board["replay"]["note"] is None
    assert board["universe"] == 1 and board["universe_symbols"] == [SYM]
    assert board["proposing"] is False and board["proposals"] == []
    assert board["replay"]["journal"]["lines"] == len(lines) + 3
    target["playhead"] = created + 0.5                    # played across the moment it was raised
    eyes.tick(0)
    [alert] = eyes.take_alerts()
    assert alert["id"] == raised["proposal"]["id"] and eyes.board(0)["proposals"][0]["status"] == "open"
    target["playhead"] = created - 1                      # scrubbed back ...
    eyes._last_rebuild = 0.0
    eyes.tick(0)
    assert eyes.board(0)["proposals"] == []
    target["playhead"] = created + 3600                   # ... then jumped past it: nothing pops up
    eyes.tick(0)
    assert eyes.take_alerts() == []


def test_the_default_target_plays_the_journal_back_off_the_edge_unless_a_session_record_is_loaded(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from eyes import sim_eyes
    from sim import mode, replay, session_clock

    at = datetime(2026, 9, 24, 8, 7, 2, tzinfo=ZoneInfo("America/New_York"))
    monkeypatch.setattr(mode, "is_replay_desk", lambda: True)
    monkeypatch.setattr(session_clock, "now_et", lambda: at)
    monkeypatch.setattr(replay, "status_payload", lambda: {"replay_source": "none", "replay_ok": True})
    assert sim_eyes._default_target() == {"kind": "journal", "date": "2026-09-24", "playhead": at.timestamp(),
                                          "symbol": None, "loaded": None}
    monkeypatch.setattr(replay, "status_payload", lambda: {"replay_source": "historical", "replay_ok": True,
                                                           "replay_symbol": "PFSA", "replay_date": "2026-09-24"})
    assert sim_eyes._default_target()["kind"] == "journal" and sim_eyes._default_target()["symbol"] == "PFSA"
    monkeypatch.setattr(replay, "status_payload", lambda: {"replay_source": "capture", "replay_ok": True,
                                                           "replay_symbol": "PFSA", "replay_date": "2026-09-24"})
    assert sim_eyes._default_target()["kind"] == "capture"
    monkeypatch.setattr(mode, "is_replay_desk", lambda: False)
    assert sim_eyes._default_target() is None


def test_the_engine_beats_once_a_minute(tmp_path):
    from setup_scanner.engine import SetupEngine

    seen: list[dict] = []
    clock = {"t": 1000.0}
    eng = SetupEngine(templates=lambda: TemplateStore(tmp_path / "t.json"), journal=seen.append,
                      universe=lambda: [], bot_state=dict, setups=("first_pullback",), clock=lambda: clock["t"])
    for now in (1000.0, 1030.0, 1061.0):
        clock["t"] = now
        asyncio.run(eng.tick(now))
    assert [e["ts"] for e in seen if e["event"] == "beat"] == [1000.0, 1061.0]


def test_the_at_route_folds_the_day_to_the_moment(tmp_path, monkeypatch):
    from eyes import routes

    monkeypatch.setenv("NOVA_EYES_DIR", str(tmp_path))
    set_store_for_tests(TemplateStore(tmp_path / "t.json"))
    t = 1_790_250_000.0
    write(tmp_path / "journal" / f"{DAY}.jsonl", header(t))
    app = FastAPI()
    app.include_router(routes.router)
    c = TestClient(app)
    got = c.get("/api/eyes/at", params={"date": DAY, "at": t + 5}).json()
    assert got["date"] == DAY and got["universe"] == 1 and got["gap"] is None
    assert [s["id"] for s in got["setups"]] == list(BOT_SCANNER_SETUPS)
    assert all(s["recorded"] and s["window"]["start"] for s in got["setups"])
    assert c.get("/api/eyes/at", params={"date": "24-09-2026", "at": t}).status_code == 400
    assert json.dumps(board_at(tmp_path / "none.jsonl", DAY, t, levels={}))    # no file: a stated absence
