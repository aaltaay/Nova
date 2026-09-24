"""In the Sim venue, sensors read the loaded replay through the shared pipes."""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app
from sensors import rings
from sim import practice
from sim.mode import reset_for_tests, set_sim_mode

client = TestClient(app)


def setup_function() -> None:
    reset_for_tests()
    rings.reset_for_tests()
    set_sim_mode(True)


def teardown_function() -> None:
    reset_for_tests()
    rings.reset_for_tests()


def test_snapshot_defaults_to_the_liquid_symbol_with_nothing_loaded():
    res = client.get("/sensors/snapshot")
    assert res.status_code == 200
    assert res.json()["symbol"] == "AAPL"
    assert res.json()["count"] == 20


def test_snapshot_defaults_to_the_loaded_replay_symbol(monkeypatch):
    monkeypatch.setattr(practice, "loaded", lambda: practice.Loaded("historical", "IMCC", ("k",)))
    assert client.get("/sensors/snapshot").json()["symbol"] == "IMCC"


def test_replayed_book_is_labelled_replay_not_ibkr(monkeypatch):
    from ibkr.depth import state as depth_state
    from sensors import feeds

    book = {"bids": [{"price": 9.9, "size": 100}], "asks": [{"price": 10.1, "size": 100}]}
    monkeypatch.setattr(depth_state, "current_book", lambda symbol: book if symbol == "IMCC" else None)
    assert feeds.get_book("IMCC") == (book, "replay")
    assert feeds.get_book("SPY") == (None, None)
