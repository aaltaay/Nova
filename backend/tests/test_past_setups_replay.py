"""The setups that ended, on a Sim replay, are the Sim eyes' up to the playhead and nothing after it (ADR 052
amendment, #815).

The morning: a first pullback arms, a candle breaks its low and every setup fails, then the stock runs and fades --
so the setups that ended have a "what price did next" that is still open, then settled, as the playhead plays on.

- No lookahead: the past setups at any moment read the same as the Sim eyes over the recording cut at that moment,
  their "what price did next" included.
- A rewind answers nothing until the lanes are rebuilt at the new playhead, then what a fresh build there answers.
- The route answers them on a replay desk.
"""
from __future__ import annotations

from types import SimpleNamespace

from eyes.recording import Recording
from eyes.sim_eyes import SimEyes
from setup_templates.store import TemplateStore, set_store_for_tests
from stock_read import past_setups
from tests.setup_scanner_fixtures import add, base_morning, leg_up
from tests.test_sim_eyes_replay import _cut

DAY, SYM = "2026-09-21", "ABCD"
KEY = ["capture", SYM, DAY]
LEVELS = {"chosen": "first_pullback", "levels": {"first_pullback": 2, "bull_flag": 2, "flat_top_breakout": 2,
                                                "red_to_green": 2}}


def recording() -> Recording:
    b = add(leg_up(base_morning(), [4.08, 4.18, 4.28, 4.38]), 4.38, 4.37, 4.30, 4.32, 30_000)
    b = add(b, 4.32, 4.33, 4.12, 4.15, 60_000)          # breaks the pullback's low: the setups fail
    for o, h, lo, c in [(4.15, 4.22, 4.14, 4.20), (4.20, 4.30, 4.19, 4.28), (4.28, 4.45, 4.27, 4.44),
                        (4.44, 4.60, 4.40, 4.58), (4.58, 4.70, 4.55, 4.66), (4.66, 4.68, 4.50, 4.52)]:
        b = add(b, o, h, lo, c, 50_000)
    return Recording(date=DAY, symbol=SYM, prints=[], print_ts=[], ticks=[], books=[], book_ts=[], bars=b,
                     bars_source="archive", spans=[], prev_close=3.0)


def eyes_over(rec: Recording, target: dict, tmp_path) -> SimEyes:
    return SimEyes(target=lambda: dict(target), load=lambda d, s: rec, journal=lambda e: None, threaded=False,
                   levels=lambda: LEVELS, journal_path=lambda d: tmp_path / f"{d}.jsonl",
                   sizing=SimpleNamespace(risk_usd=lambda: 20.0, order_shares=lambda risk: 100))


def past(eyes: SimEyes, at: float, five: bool = False) -> dict:
    return past_setups.replay(SYM, None, five=five, eyes=eyes, playhead=at)


def test_the_past_setups_at_any_moment_read_nothing_after_it(tmp_path):
    set_store_for_tests(TemplateStore(tmp_path / "t.json"))
    rec = recording()
    start, end = rec.bars[38].t, rec.bars[-1].t + 120
    target = {"kind": "capture", "date": DAY, "symbol": SYM, "playhead": start, "replay_key": KEY}
    full = eyes_over(rec, target, tmp_path)
    seen = {"pending": 0, "settled": 0, "episodes": 0}
    t = start
    while t <= end:
        target["playhead"] = t
        full.tick(0)
        cut_target = dict(target)
        cut = eyes_over(_cut(rec, t), cut_target, tmp_path)
        cut.tick(0)
        for five in (False, True):
            got, want = past(full, t, five), past(cut, t, five)
            assert got == want, f"the past setups at {(t - start) / 60:+.1f} min read past the moment"
        body = past(full, t)
        assert body["replay"] is True and body["pending"] is False and body["generated_at"] == t
        assert all(e["after"] is None or e["after"]["from_ts"] <= t for e in body["episodes"])
        seen["episodes"] = max(seen["episodes"], len(body["episodes"]))
        firsts = [e["after"]["first"] for e in body["episodes"] if e["after"]]
        seen["pending"] += firsts.count("pending")
        seen["settled"] += sum(1 for f in firsts if f in ("high", "low"))
        t += 20
    assert seen["episodes"] >= 4 and seen["pending"] and seen["settled"], seen


def test_what_price_did_next_reads_only_candles_the_playhead_completed(tmp_path):
    set_store_for_tests(TemplateStore(tmp_path / "t.json"))
    rec = recording()
    fail_bar = rec.bars[45]                                  # the candle that broke the pullback's low
    target = {"kind": "capture", "date": DAY, "symbol": SYM, "playhead": fail_bar.t + 90, "replay_key": KEY}
    eyes = eyes_over(rec, target, tmp_path)
    eyes.tick(0)
    at = target["playhead"]
    body = past(eyes, at)
    [ep] = [e for e in body["episodes"] if e["setup_type"] == "first_pullback" and e["died_at"] is not None]
    assert body["bars"]["count"] == sum(1 for b in rec.bars if b.t + 60 <= at)      # never the forming candle
    # It died at the failing candle's close; the next candle (high 4.22) is still forming at the playhead.
    assert ep["after"]["first"] == "pending" and ep["after"]["complete"] is False
    assert ep["after"]["bars"] == 0 and ep["after"]["high"] is None
    target["playhead"] = at + 60                              # that candle closes: it is read, nothing later
    eyes.tick(0)
    [ep] = [e for e in past(eyes, at + 60)["episodes"] if e["setup_type"] == "first_pullback" and e["died_at"]]
    assert ep["after"]["bars"] == 1 and ep["after"]["high"] == 4.22


def test_a_rewind_answers_nothing_until_the_lanes_are_rebuilt_at_the_new_playhead(tmp_path):
    set_store_for_tests(TemplateStore(tmp_path / "t.json"))
    rec = recording()
    late, early = rec.bars[-1].t + 60, rec.bars[46].t + 30
    target = {"kind": "capture", "date": DAY, "symbol": SYM, "playhead": late, "replay_key": KEY}
    eyes = eyes_over(rec, target, tmp_path)
    eyes.tick(0)
    assert past(eyes, late)["episodes"]
    target["playhead"] = early                               # back, inside the rebuild throttle: not rebuilt yet
    eyes.tick(0)
    body = past(eyes, early)
    assert body["episodes"] == [] and body["pending"] is True and "catching up" in body["note"]
    eyes._last_rebuild = 0                                   # the throttle lets the rebuild run
    eyes.tick(0)
    fresh = eyes_over(rec, dict(target), tmp_path)
    fresh.tick(0)
    assert past(eyes, early) == past(fresh, early)


def test_another_symbol_or_another_day_reads_nothing(tmp_path):
    set_store_for_tests(TemplateStore(tmp_path / "t.json"))
    rec = recording()
    target = {"kind": "capture", "date": DAY, "symbol": SYM, "playhead": rec.bars[-1].t, "replay_key": KEY}
    eyes = eyes_over(rec, target, tmp_path)
    eyes.tick(0)
    other = past_setups.replay("ZZZZ", None, eyes=eyes, playhead=rec.bars[-1].t)
    assert other["episodes"] == [] and "nothing of ZZZZ is loaded" in other["note"]
    day = past_setups.replay(SYM, "2026-09-22", eyes=eyes, playhead=rec.bars[-1].t)
    assert day["episodes"] == [] and "the replay is 2026-09-21" in day["note"]


def test_the_route_answers_the_sim_eyes_setups_on_a_replay_desk(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import eyes.sim_eyes as sim_eyes_mod
    from main import app
    from sim.mode import set_venue

    set_store_for_tests(TemplateStore(tmp_path / "t.json"))
    rec = recording()
    target = {"kind": "capture", "date": DAY, "symbol": SYM, "playhead": rec.bars[-1].t, "replay_key": KEY}
    eyes = eyes_over(rec, target, tmp_path)
    eyes.tick(0)
    monkeypatch.setattr(sim_eyes_mod, "get_sim_eyes", lambda: eyes)
    set_venue("sim", persist=False)                          # the suite pins Sim's live edge off: a replay desk
    body = TestClient(app).get(f"/api/stock-read/{SYM}/past-setups").json()
    assert body["replay"] is True and body["date"] == DAY and body["schema_version"] == 1
    assert body["episodes"] == past(eyes, eyes.board(0)["replay"]["at"])["episodes"]
    assert body["counts"]["failed"] >= 4
