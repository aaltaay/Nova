"""A Session Record's folder is named in one place and stays inside the capture root.

CodeQL path-injection alerts 12-17, 23-25 and 108: ``POST /api/sim/replay {date, symbol}`` and
``POST /api/eyes/backtests`` ``sessions[].symbol`` reached ``<capture root>/<date>/<SYMBOL>``
unchecked, so ``..``, an absolute path, a drive letter or a ``\\\\host\\share`` path could
leave the capture folder. ``capture.storage.session_path`` refuses them with the reason; a
real date and ticker still load from the same folder as before.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from capture import sessions
from capture.storage import session_path
from sim import capture_player as player, replay, session_clock as clock

DAY = "2026-09-18"
TS = datetime.fromisoformat("2026-09-18T10:00:00-04:00").timestamp()

CRAFTED_SYMBOLS = [
    "../x", "..\\x", "../../Windows/win.ini", "..\\..\\Windows", "..", ".", "A/B", "A\\B",
    "C:", "C:/x", "C:\\x", "/etc/passwd", "\\\\host\\share", "//host/share",
    "", " AAPL", "AAPL ", "AA PL", "A..", "A.", "AAPL\n", "A" * 13, "1ABC",
]
CRAFTED_DATES = [
    "../2026-09-18", "..\\2026-09-18", "2026-09-18/..", "2026-09-18\\..\\..", "C:/x", "C:\\x", "D:",
    "/etc", "\\\\host\\share", "", " 2026-09-18", "2026-09-18 ", "2026-09-18\n", "2026-9-18",
    "\u0662\u0660\u0662\u0666-\u0660\u0669-\u0661\u0668",   # Arabic-Indic digits: ASCII only
]


# -- the guard ------------------------------------------------------------------------------------
@pytest.mark.parametrize("symbol", ["AAPL", "aapl", "IMCC", "SIM1", "L2TEST", "PENDING", "BRK.B", "BF-B", "A"])
def test_a_real_date_and_ticker_name_the_same_folder_as_before(tmp_path, symbol):
    got = session_path(DAY, symbol, root=tmp_path)
    assert got == tmp_path / DAY / symbol.upper()
    assert str(got) == str(tmp_path / DAY / symbol.upper())     # the recorder's own string, unchanged
    assert not got.exists()                                     # naming a folder never creates one


@pytest.mark.parametrize("symbol", CRAFTED_SYMBOLS)
def test_a_crafted_symbol_is_refused_with_the_reason(tmp_path, symbol):
    with pytest.raises(ValueError, match="symbol is a ticker"):
        session_path(DAY, symbol, root=tmp_path)


@pytest.mark.parametrize("date", CRAFTED_DATES)
def test_a_crafted_date_is_refused_with_the_reason(tmp_path, date):
    with pytest.raises(ValueError, match="date is YYYY-MM-DD"):
        session_path(date, "AAPL", root=tmp_path)


def test_none_is_refused_not_turned_into_a_folder(tmp_path):
    with pytest.raises(ValueError, match="date"):
        session_path(None, "AAPL", root=tmp_path)            # type: ignore[arg-type]
    with pytest.raises(ValueError, match="symbol"):
        session_path(DAY, None, root=tmp_path)               # type: ignore[arg-type]


def test_a_refusal_repeats_only_the_start_of_a_long_name(tmp_path):
    with pytest.raises(ValueError) as err:
        session_path(DAY, "A/" * 500, root=tmp_path)
    assert len(str(err.value)) < 200


def test_a_root_written_loosely_or_at_a_drive_root_still_works(tmp_path):
    loose = str(tmp_path) + os.sep + "." + os.sep
    assert session_path(DAY, "AAPL", root=loose) == tmp_path / DAY / "AAPL"
    anchor = Path(tmp_path.anchor)                           # C:\ on Windows, / elsewhere
    assert session_path(DAY, "AAPL", root=anchor) == anchor / DAY / "AAPL"


def test_no_root_given_uses_the_capture_root(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SIM_CAPTURE_DIR", str(tmp_path))
    assert session_path(DAY, "AAPL") == tmp_path / DAY / "AAPL"


# -- the Sim replay (POST /api/sim/replay) --------------------------------------------------------
@pytest.fixture
def captures(tmp_path, monkeypatch):
    root = tmp_path / "captures"
    root.mkdir()
    replay.reset_for_tests()
    clock.reset_for_tests()
    monkeypatch.setattr(player, "capture_root", lambda: root)
    monkeypatch.setattr(sessions, "capture_root", lambda: root)
    yield root
    replay.reset_for_tests()
    clock.reset_for_tests()


def _write_session(folder: Path, symbol: str = "IMCC") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    row = {"ts": TS, "symbol": symbol, "price": 12.5, "size": 7}
    (folder / "prints.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    return folder


def test_a_real_session_still_loads_from_its_folder(captures):
    folder = _write_session(captures / DAY / "IMCC")
    info = player.load(DAY, "imcc")
    assert info["ok"] is True and info["dir"] == str(folder) and info["counts"]["prints"] == 1
    assert player.is_loaded()


@pytest.mark.parametrize("date,symbol", [
    (DAY, "../outside/2026-09-18/IMCC"), (DAY, "..\\outside"), (DAY, "..\\..\\outside"), (DAY, "../../outside"),
    ("../outside", "IMCC"),
    ("..\\..\\outside", "IMCC"), (DAY, "C:/x"), ("C:\\x", "IMCC"), (DAY, "\\\\host\\share"), ("", "IMCC"),
])
def test_the_player_refuses_a_crafted_pick_and_reads_nothing_outside(captures, date, symbol):
    # A real recording sits next to the capture folder; a crafted pick never reaches it.
    _write_session(captures.parent / "outside" / DAY / "IMCC")
    _write_session(captures.parent / "outside")
    info = player.load(date, symbol)
    assert info["ok"] is False and ("YYYY-MM-DD" in info["error"] or "ticker" in info["error"])
    assert not player.is_loaded()


def test_set_replay_states_the_refusal_on_screen(captures):
    result = replay.set_replay(DAY, "..\\..\\x")
    assert result["replay_ok"] is False
    assert "ticker" in result["replay_error"]                 # the reason, not "Could not read capture"
    assert not player.is_loaded()


# -- the eyes (POST /api/eyes/backtests, the Sim eyes) ---------------------------------------------
@pytest.mark.parametrize("date,symbol", [(DAY, "../x"), (DAY, "..\\..\\x"), ("../x", "AAA"), (DAY, "C:\\x"),
                                         (DAY, "\\\\host\\share"), (DAY, "")])
def test_the_eyes_loader_refuses_a_crafted_session(tmp_path, date, symbol):
    from eyes.recording import load

    _write_session(tmp_path / "x")
    with pytest.raises(ValueError, match="YYYY-MM-DD|ticker"):
        load(date, symbol, root=tmp_path / "captures", bars_fn=lambda sym, day: [])


def test_a_backtest_skips_a_crafted_session_with_the_reason(tmp_path, monkeypatch):
    """The real loader: a crafted symbol is refused before the capture root is looked up."""
    from eyes import backtest

    monkeypatch.setenv("NOVA_EYES_DIR", str(tmp_path / "eyes"))
    monkeypatch.setenv("NOVA_SIM_CAPTURE_DIR", str(tmp_path / "captures"))
    man = backtest.run(sessions=[(DAY, "..\\..\\x"), (DAY, "C:/x")], run_id="20260918-100000-abcdef")
    assert [s["status"] for s in man["sessions"]] == ["skipped", "skipped"]
    assert all("ticker" in s["reason"] for s in man["sessions"])


# -- the open segment still matches the recorder's folder ------------------------------------------
def test_recording_here_matches_the_recorders_folder_however_the_root_is_written(tmp_path, monkeypatch):
    from capture import recorder
    from sim.capture_spans import recording_here

    loose = str(tmp_path) + os.sep + "." + os.sep + DAY + os.sep + "AAA"
    monkeypatch.setattr(recorder, "status", lambda: {"sessions": {"AAA": {"recording": True, "dir": loose}}})
    assert recording_here(session_path(DAY, "AAA", root=tmp_path))
    assert not recording_here(session_path(DAY, "BBB", root=tmp_path))
