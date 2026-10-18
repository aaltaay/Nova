"""The stock read on a Sim replay desk is the replay's at the playhead, and reads nothing after it (ADR 052).

The window is a real historical replay in a private Sim store (the IBKR download path): 07:00:10 10.00,
07:00:30 11.00, 07:00:45 10.40, 07:01:00 12.00, 07:01:30 10.00.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from main import app
from sim import session_clock as clock
from sim.mode import set_venue
from stock_read import routes
from tests.test_bot_sim_replay import DAY, SYM, go, load_window
from tests.test_sim_practice import isolated  # noqa: F401 -- autouse: a private Sim store and clean replay

client = TestClient(app)


def _read() -> dict:
    routes._cache.clear()
    res = client.get(f"/api/stock-read/{SYM}")
    assert res.status_code == 200
    return res.json()


def test_the_read_is_the_replays_at_the_playhead_and_never_later():
    set_venue("sim", persist=False)
    load_window()
    go(75)                                              # 07:01:15: the 07:00 candle is done, 07:01's is not
    read = _read()
    assert read["replay"] is True and read["session_date"] == DAY
    assert read["generated_at"] == clock.now_et().timestamp()
    assert read["price"] == 12.00                       # the last print by then
    assert read["levels"]["hod"]["price"] == 11.00     # the 12.00 print is in a candle still forming
    go(150)                                             # 07:02:30: the 07:01 candle is done
    assert _read()["levels"]["hod"]["price"] == 12.00
    go(20)                                              # back: nothing from later
    read = _read()
    assert read["levels"]["hod"] is None and read["price"] == 10.00


def test_a_rewind_is_never_served_a_cached_later_read():
    set_venue("sim", persist=False)
    load_window()
    go(150)
    routes._cache.clear()
    assert client.get(f"/api/stock-read/{SYM}").json()["levels"]["hod"]["price"] == 12.00
    go(20)                                              # the cache holds the 07:02:30 read: not served at 07:00:20
    assert client.get(f"/api/stock-read/{SYM}").json()["levels"]["hod"] is None


def test_the_whole_day_routes_answer_nothing_on_a_replay():
    """The decisions timeline reads whole days; the past setups are the Sim eyes' own (#815,
    ``test_past_setups_replay``), and none until the Sim eyes have read the replay."""
    set_venue("sim", persist=False)
    load_window()
    go(75)
    past = client.get(f"/api/stock-read/{SYM}/past-setups").json()
    assert past["replay"] is True and past["episodes"] == [] and past["pending"] is True
    assert "reading the replay" in past["note"]
    decisions = client.get(f"/api/stock-read/{SYM}/decisions").json()
    assert decisions["replay"] is True and decisions["events"] == []
    flush = client.get(f"/api/stock-read/{SYM}/flush").json()
    assert flush["score"] is None and flush["label"] == "blind"


def test_the_daily_map_reads_only_the_days_before_the_replayed_one(monkeypatch):
    from stock_read import history

    def day(d: str, high: float) -> dict:
        t = datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp()
        return {"t": t, "o": 5.0, "h": high, "l": 4.0, "c": 5.0, "v": 1e6}

    bars = [day("2026-09-16", 6.0), day("2026-09-17", 7.0), day(DAY, 50.0), day("2026-09-21", 90.0)]
    monkeypatch.setattr("sensors.feeds.get_bars", lambda sym, tf, limit, **_k: (bars, "ibkr"))
    history._cache.clear()
    now = datetime.fromisoformat(f"{DAY}T09:00:00-04:00").timestamp()
    out = history.summary(SYM, now, replay=True)
    assert [b["d"] for b in out["daily"]] == ["2026-09-16", "2026-09-17"]     # never the day itself, or later
    live = history.summary(SYM, now)
    assert [b["d"] for b in live["daily"]][-1] == "2026-09-21"                 # the live read is unchanged


def test_replay_read_populates_playhead_volume_liquidity_luld_and_float_detail(monkeypatch):
    from luld import replay as luld_replay
    from sim import history_playback as playback, history_store as store
    from stock_read import replay_read

    set_venue("sim", persist=False)
    load_window()
    go(75)                                              # 07:01:15: 4 prints of 100 shares = 400 shares traded so far
    assert replay_read._price(SYM)["volume"] == 400
    monkeypatch.setattr(
        luld_replay,
        "view",
        lambda sym: {
            "schema_version": 1,
            "symbol": sym,
            "source": "replay",
            "state": "bands",
            "exact": True,
            "lower": 9.0,
            "upper": 11.0,
            "tier_sure": True,
            "distance": {"down_pct": -0.25, "up_pct": -0.0833},
            "near": None,
            "reason": None,
            "text": "LULD 9.00 - 11.00",
            "as_of": clock.now_et().timestamp(),
        },
    )
    body = _read()
    groups = {g["id"]: {r["id"]: r for r in g["rows"]} for g in body["groups"]}
    # Volume at the playhead is known (400 shares @ ~$10 = ~$4K, which is under the $2M day floor, never "unknown").
    liq = groups["in_play"]["liquidity"]
    assert liq["state"] == "bad" and "traded $4K today" in (liq["detail"] or "")
    # Float unknown on replay explains that historical float is not recorded rather than blaming today's Yahoo feed.
    fl = groups["float"]["float"]
    assert fl["state"] == "unknown" and "Yahoo gave none" not in (fl["detail"] or "")
    # Halts group includes the replay LULD reading.
    luld_row = groups["halts"]["luld"]
    assert luld_row["value"] == "9.00 - 11.00" and luld_row["state"] == "info"

    # With sufficient replay volume (300,000 shares @ $10 = $3.0M traded today and in the last 5 minutes), liquidity is ok.
    spec = store.window(SYM, DAY, "04:00", "10:00")
    job = store.create(spec, "trades")
    a = spec["start_ts"]
    store.commit_page(job["id"], a, [dict(ts=a + 10, price=10.0, size=300_000)], spec["end_ts"], True)
    playback.select(spec)
    go(75)
    body_liquid = _read()
    liq_ok = {g["id"]: {r["id"]: r for r in g["rows"]} for g in body_liquid["groups"]}["in_play"]["liquidity"]
    assert liq_ok["state"] == "ok" and liq_ok["value"] == "$3.00M"


