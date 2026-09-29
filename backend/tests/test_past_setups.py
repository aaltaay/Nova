"""`GET /api/stock-read/{symbol}/past-setups` and the study of setups that ended (ADR 036 amendment,
operator ask 2026-09-29): today's journal folded as it grows, each failed setup with what price did
next, a source that cannot be read said so -- and the same episodes totalled by reason across days."""
from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from eyes import failure_study
from stock_read import past_setups, routes
from tests.test_setup_episodes import DAY, NCPL_BARS, at, line, ncpl_lines


def write(path, lines: list[dict]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        for row in lines:
            fh.write(json.dumps(row) + "\n")


def test_today_is_folded_as_it_grows_and_each_failure_says_what_came_next(tmp_path, monkeypatch):
    monkeypatch.setattr(past_setups, "_today", None)
    path = tmp_path / f"{DAY}.jsonl"
    write(path, ncpl_lines()[:3])
    asked: list[tuple[str, str]] = []

    def bars_fn(sym: str, date: str):
        asked.append((sym, date))
        return NCPL_BARS

    body = past_setups.read("ncpl", DAY, at(9, 22), today=True, path=path, bars_fn=bars_fn)
    [ep] = body["episodes"]
    assert ep["end"] is None and ep["died_at"] == at(9, 20, 0.42)       # failed, still on the scanner
    assert ep["after"]["first"] == "high" and not ep["after"]["complete"]
    assert body["counts"] == {"failed": 0, "faded": 0, "triggered": 0, "cut": 0, "open": 1}
    assert body["journal"] == {"ok": True, "error": None, "lines": 3} and asked == [("NCPL", DAY)]
    write(path, ncpl_lines()[3:])
    body = past_setups.read("NCPL", DAY, at(9, 40), today=True, path=path, bars_fn=bars_fn)
    [ep] = body["episodes"]
    assert ep["end"] == "failed" and ep["ended_by"] == "no pole" and ep["after"]["complete"]
    assert body["journal"]["lines"] == 4 and body["counts"]["failed"] == 1


def test_a_source_that_cannot_be_read_is_said_and_the_rest_answers(tmp_path, monkeypatch):
    monkeypatch.setattr(past_setups, "_today", None)
    path = tmp_path / f"{DAY}.jsonl"
    write(path, ncpl_lines())

    def broken(sym: str, date: str):
        raise OSError("archive.db is locked")

    body = past_setups.read("NCPL", DAY, at(10, 0), today=False, path=path, bars_fn=broken)
    assert body["bars"] == {"ok": False, "error": "OSError: archive.db is locked", "count": 0}
    assert body["episodes"][0]["end"] == "failed" and body["episodes"][0]["after"] is None

    def no_journal(*a, **k):
        raise PermissionError("journal")

    monkeypatch.setattr(past_setups, "episodes_of", no_journal)
    body = past_setups.read("NCPL", DAY, at(10, 0), today=False, path=path, bars_fn=broken)
    assert body["journal"]["ok"] is False and body["episodes"] == [] and body["bars"]["ok"] is True


def test_a_day_is_found_by_listing_its_folder_and_a_day_with_no_file_says_so(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_EYES_DIR", str(tmp_path))
    monkeypatch.setattr(past_setups, "_today", None)
    folder = tmp_path / "journal"
    folder.mkdir()
    write(folder / f"{DAY}.jsonl", ncpl_lines())
    from eyes import journal

    assert journal.day_path(DAY) == folder / f"{DAY}.jsonl"
    assert journal.day_path("../../etc/passwd") is None           # only ever compared with file names
    body = past_setups.read("NCPL", DAY, at(10, 0), today=True, bars_fn=lambda s, d: NCPL_BARS)
    assert body["journal"]["ok"] and body["episodes"][0]["end"] == "failed"
    body = past_setups.read("NCPL", "2026-09-28", at(10, 0), today=False, bars_fn=lambda s, d: NCPL_BARS)
    assert body["journal"] == {"ok": False, "error": "no eyes' journal on file for 2026-09-28", "lines": 0}
    assert body["episodes"] == []


def test_the_route_answers_the_day_and_refuses_a_bad_date(monkeypatch):
    seen = {}

    def fake(sym, day, now, *, today):
        seen.update(sym=sym, day=day, today=today)
        return {"symbol": sym, "date": day, "generated_at": now, "episodes": [], "counts": {},
                "journal": {"ok": True, "error": None, "lines": 0}, "bars": {"ok": True, "error": None, "count": 0}}

    monkeypatch.setattr(past_setups, "read", fake)
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)
    res = client.get("/api/stock-read/ncpl/past-setups?date=2026-09-28")
    assert res.status_code == 200 and res.json()["schema_version"] == 1
    assert seen == {"sym": "NCPL", "day": "2026-09-28", "today": False}
    assert client.get("/api/stock-read/NCPL/past-setups?date=yesterday").status_code == 400
    assert client.get("/api/stock-read/NCPL/past-setups").status_code == 200 and seen["today"] is True


def test_the_study_totals_the_failures_by_rule_and_leaves_out_a_faded_leg(tmp_path):
    path = tmp_path / f"{DAY}.jsonl"
    other = [{**row, "symbol": "ABCD"} for row in ncpl_lines()]
    leg = {"t": at(10, 0), "high": 2.0, "low": 1.8, "pct": 0.11}
    faded = [line("leg", at(10, 1), sym="WXYZ", lane="flat_top_breakout", leg=leg, reason="new high of day 2.00"),
             line("state", at(10, 2), sym="WXYZ", lane="flat_top_breakout", state="watching", leg=None,
                  reason="no base under the high of day")]
    write(path, ncpl_lines() + other + faded)
    body = failure_study.study([(DAY, path)], bars_fn=lambda sym, date: NCPL_BARS if sym == "NCPL" else [],
                               now=at(12, 0), listing=True)
    [group] = body["groups"]
    assert group["setup_type"] == "bull_flag" and group["end"] == "failed" and group["count"] == 2
    assert group["reason_key"] == "flag candle # made a higher high than the candle before it"
    assert group["first"]["high"] == 1 and group["first"]["unknown"] == 1
    assert group["trade"]["n"] == 1 and group["trade"]["open"] == 1
    assert body["left_out_legs"] == 1 and body["missing_bars"] == [f"ABCD {DAY}"]
    assert [e["symbol"] for e in body["episodes"]] == ["NCPL", "ABCD"]
    legs = failure_study.study([(DAY, path)], bars_fn=lambda sym, date: [], now=at(12, 0), include_legs=True,
                               setup="flat_top_breakout")
    assert [(g["end"], g["count"]) for g in legs["groups"]] == [("faded", 1)]
