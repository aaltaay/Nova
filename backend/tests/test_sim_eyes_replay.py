"""The Sim eyes on a loaded replay hand Nova's bot its triggers, and never show what comes later (ADR 052).

- A trigger the playhead plays across goes to the trigger listeners, stamped with the replay's key; one a jump
  or a rebuild passed over never does.
- After a rewind, until the lanes are rebuilt at the new playhead, the board, the cards and the chart's read
  say they are catching up -- never the lanes as they stood later.
- A historical window becomes the lanes' recording: the window's NBBO as a one-level book sampled inside the
  downloaded span, each print's side from the quote strictly before it, nothing outside the span.
"""
from __future__ import annotations

from types import SimpleNamespace

from eyes.history_recording import from_selection, nbbo_books
from eyes.sim_eyes import SimEyes
from setup_templates.store import TemplateStore, set_store_for_tests
from sim.history_quotes import QuoteSeries
from tests.test_eyes import DAY, SYM, recording

KEY = ["capture", SYM, DAY]
LEVELS = {"chosen": "first_pullback", "levels": {"first_pullback": 2}}


def _eyes(tmp_path, target: dict, heard: list) -> SimEyes:
    set_store_for_tests(TemplateStore(tmp_path / "t.json"))
    rec = recording()
    eyes = SimEyes(target=lambda: dict(target), load=lambda d, s: rec, journal=lambda e: None, threaded=False,
                   levels=lambda: LEVELS, journal_path=lambda d: tmp_path / f"{d}.jsonl", sizing=SimpleNamespace(
                       risk_usd=lambda: 20.0, order_shares=lambda risk: 100))
    eyes.add_trigger_listener(heard.append)
    return eyes


def _armed_at() -> float:
    return recording().bars[-1].t + 60


def test_a_trigger_the_playhead_plays_across_goes_to_the_bot_with_its_replay(tmp_path):
    heard: list[dict] = []
    target = {"kind": "capture", "date": DAY, "symbol": SYM, "playhead": _armed_at() + 2, "replay_key": KEY}
    eyes = _eyes(tmp_path, target, heard)
    eyes.tick(0)                                     # built at the playhead: nothing handed over
    assert heard == []
    for step in range(3, 40):                        # play forward a second at a time
        target["playhead"] = _armed_at() + step
        eyes.tick(0)
    assert heard, "the first pullback triggers at 4.38 while the playhead plays across it"
    event = heard[0]
    assert event["source"] == "sim" and event["replay_key"] == KEY and event["symbol"] == SYM
    assert event["setup_type"] == "first_pullback" and event["setup"]["triggered_at"] <= target["playhead"]


def test_a_jump_over_a_trigger_hands_the_bot_nothing(tmp_path):
    heard: list[dict] = []
    target = {"kind": "capture", "date": DAY, "symbol": SYM, "playhead": _armed_at() + 2, "replay_key": KEY}
    eyes = _eyes(tmp_path, target, heard)
    eyes.tick(0)
    target["playhead"] = _armed_at() + 55             # one step over the trigger and the target
    eyes.tick(0)
    assert heard == []
    board = eyes.board(0)
    assert any(r.get("state") for r in board["rows"])     # the board shows where the lanes are now


def test_a_rewind_shows_nothing_from_after_the_playhead_until_rebuilt(tmp_path):
    heard: list[dict] = []
    target = {"kind": "capture", "date": DAY, "symbol": SYM, "playhead": _armed_at() + 55, "replay_key": KEY}
    eyes = _eyes(tmp_path, target, heard)
    eyes.tick(0)
    eyes.symbol_view(SYM)                            # a reader asks: the worker builds the symbol view
    eyes.tick(0)
    assert eyes.board(0)["rows"] and eyes.symbol_view(SYM).get("setups")
    target["playhead"] = _armed_at() + 2              # back, inside the rebuild throttle: not rebuilt yet
    eyes.tick(0)
    board = eyes.board(0)
    assert board["rows"] == [] and board["proposals"] == [] and board["replay"]["loading"] is True
    assert eyes.symbol_view(SYM) == {"pending": "catching up to the playhead after a rewind"}
    eyes._last_rebuild = 0                            # the throttle lets the rebuild run
    eyes.tick(0)
    board = eyes.board(0)
    assert board["replay"]["loading"] is False and board["replay"]["at"] <= target["playhead"]
    assert heard == []                                # a rebuild hands over nothing it passed


def test_another_symbol_is_not_the_replays_and_reads_nothing(tmp_path):
    target = {"kind": "capture", "date": DAY, "symbol": SYM, "playhead": _armed_at() + 5, "replay_key": KEY}
    eyes = _eyes(tmp_path, target, [])
    eyes.tick(0)
    assert eyes.symbol_view("ZZZZ") is None


# -- no lookahead: the lanes at T read the same with the recording cut at T -------------------------
def _cut(rec, t: float):
    """The recording as it stood at ``t``: prints, books and price seconds up to ``t``; the bars that began by
    ``t`` (the forming minute's open is known once it traded; nothing reads the rest of it)."""
    from eyes.recording import Recording

    prints = [p for p in rec.prints if p["ts"] <= t]
    books = [(ts, b) for ts, b in rec.books if ts <= t]
    return Recording(date=rec.date, symbol=rec.symbol, prints=prints, print_ts=[p["ts"] for p in prints],
                     ticks=[x for x in rec.ticks if x[0] <= t], books=books, book_ts=[ts for ts, _ in books],
                     bars=[b for b in rec.bars if b.t <= t], bars_source=rec.bars_source, spans=rec.spans,
                     prev_close=rec.prev_close)


def _seen(replay) -> dict:
    """Everything the board, the cards and the bot get from the lanes at the replay's clock (a proposal's random
    id aside)."""
    from setup_scanner.board import board_body

    body = board_body(replay.playing_lanes(), replay.lanes, replay.levels(), replay.now, can_propose=True)

    def strip(x):
        if isinstance(x, dict):
            return {k: strip(v) for k, v in x.items() if k not in ("id", "proposal_id")}
        if isinstance(x, list):
            return [strip(v) for v in x]
        return x

    return {"body": strip(body), "triggers": strip(replay.triggers), "alerts": strip(
        [a for lane in replay.lanes for a in lane.alerts])}


def test_the_lanes_at_any_moment_read_nothing_after_it(tmp_path):
    from eyes.replay import EyesReplay

    store = TemplateStore(tmp_path / "t.json")
    set_store_for_tests(store)
    rec = recording()
    templates = [t for s in ("first_pullback", "bull_flag", "flat_top_breakout", "red_to_green")
                 for t in store.templates(s)]

    def replay_of(r):
        return EyesReplay(r, templates, source="sim", playing={t.setup: t.id for t in templates},
                          pillars=lambda *a, **k: {}, levels=lambda: LEVELS)

    full = replay_of(rec)
    checked = 0
    for step in range(-90, 70, 3):             # across the arming bar, the near, the trigger and the target
        t = _armed_at() + step
        full.advance(t)
        cut = replay_of(_cut(rec, t))
        cut.advance(t)
        assert _seen(full) == _seen(cut), f"the lanes at {step:+d}s read past the moment"
        checked += 1
    assert checked > 40


# -- a historical window as the lanes' recording -------------------------------------------------
def _selection(prints: list[dict], quotes: list[tuple], start: float, end: float) -> SimpleNamespace:
    class Candles:
        def bars(self, symbol, timeframe, limit, cutoff):
            return []

    spec = {"symbol": SYM, "date": DAY, "start_ts": start, "end_ts": end, "coverage": [[start, end]],
            "source": "massive"}
    return SimpleNamespace(spec=spec, prints=tuple(prints), quotes=QuoteSeries(quotes) if quotes else None,
                           prev_close=3.0, candles=Candles())


def test_a_window_reads_its_nbbo_as_a_one_level_book_inside_its_span_only():
    quotes = [(100.2, 4.10, 500, 12, 4.12, 300, 12), (101.7, 4.11, 800, 12, 4.13, 200, 12)]
    books = nbbo_books(QuoteSeries(quotes), [(100.0, 103.0)])
    assert [t for t, _ in books] == [100.5, 101.0, 101.5, 102.0, 102.5, 103.0]     # never before the first quote
    assert books[0][1]["asks"] == [{"price": 4.12, "size": 300}] and books[0][1]["l1_fallback"] is True
    assert books[2][1]["bids"] == [{"price": 4.10, "size": 500}]                     # 101.5: the quote then
    assert books[3][1]["bids"] == [{"price": 4.11, "size": 800}]                     # 102.0: the next one
    assert nbbo_books(QuoteSeries(quotes), [(200.0, 201.0)])[0][1]["bids"][0]["price"] == 4.11
    assert nbbo_books(None, [(100.0, 103.0)]) == []


def test_a_print_takes_its_side_from_the_quote_strictly_before_it():
    quotes = [(100.0, 4.10, 500, 12, 4.12, 300, 12), (101.0, 4.20, 500, 12, 4.22, 300, 12)]
    prints = [{"ts": 100.5, "price": 4.12, "size": 100, "exchange": "NASDAQ", "sets_price": True},
              {"ts": 101.0, "price": 4.12, "size": 100, "exchange": "FINRA", "sets_price": True},   # same instant
              {"ts": 101.5, "price": 4.20, "size": 50, "exchange": "NASDAQ", "sets_price": False}]
    rec = from_selection(_selection(prints, quotes, 100.0, 102.0), bars_fn=lambda s, d: [])
    assert [p["side"] for p in rec.prints] == ["ask", "ask", "bid"]          # 101.0 reads the 100.0 quote
    assert [p["sets_price"] for p in rec.prints] == [True, True, False]
    assert rec.ticks == [(101.0, 4.12, 4.12), (102.0, 4.12, 4.12)]        # an odd lot never sets the price
    assert rec.summary()["book"] == "nbbo" and rec.spans == [(100.0, 102.0)] and rec.prev_close == 3.0
    assert prints[0].get("side") is None                                   # the window's own rows untouched


def test_an_ibkr_download_has_no_book_and_no_sides():
    prints = [{"ts": 100.5, "price": 4.12, "size": 100, "exchange": "NASDAQ"}]
    rec = from_selection(_selection(prints, [], 100.0, 102.0), bars_fn=lambda s, d: [])
    assert rec.books == [] and rec.prints[0]["side"] is None and rec.summary()["book"] == "none"
