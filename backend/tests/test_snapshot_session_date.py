"""Scanner snapshots are dated by their exchange session, not the wall date (#483).

On 2026-09-22 ``/api/history/dates?type=afterhours`` offered 2026-09-19 (Sat)
and 2026-09-20 (Sun): Friday's board re-persisted on the weekend was saved
under the weekend's date, and the past-day menu offered "Sat Sep 19".
"""
from __future__ import annotations

import json

import cache as cache_mod


def _at(monkeypatch, tmp_path, session_key: str) -> None:
    monkeypatch.setattr("cache._CACHE_DIR", str(tmp_path))
    monkeypatch.setattr("cache._today_et", lambda: session_key)


def _plant(tmp_path, prefix: str, day: str, rows: list[dict]) -> None:
    (tmp_path / f"{prefix}-{day}.json").write_text(
        json.dumps({"date": day, "ts": 1.0, prefix: rows}), encoding="utf-8",
    )


def test_weekend_save_lands_on_fridays_file(tmp_path, monkeypatch):
    _at(monkeypatch, tmp_path, "2026-09-19")  # Saturday
    cache_mod.save_afterhours_snapshot([{"symbol": "WHLR"}], 5.0)

    assert not (tmp_path / "afterhours-2026-09-19.json").exists()
    data = json.loads((tmp_path / "afterhours-2026-09-18.json").read_text(encoding="utf-8"))
    assert data["date"] == "2026-09-18"
    assert data["afterhours"][0]["symbol"] == "WHLR"


def test_weekend_restart_still_restores_the_last_sessions_board(tmp_path, monkeypatch):
    _at(monkeypatch, tmp_path, "2026-09-18")  # Friday
    cache_mod.save_gainer_snapshot([{"symbol": "IPDN"}], 7.0)

    _at(monkeypatch, tmp_path, "2026-09-20")  # Sunday
    rows, ts = cache_mod.load_gainer_snapshot()
    assert [r["symbol"] for r in rows] == ["IPDN"]
    assert ts == 7.0


def test_holiday_belongs_to_the_session_before_it(tmp_path, monkeypatch):
    _at(monkeypatch, tmp_path, "2026-09-07")  # Labor Day (Monday)
    cache_mod.save_gapper_snapshot([{"symbol": "GRML"}], 1.0)
    cache_mod.save_large_cap_snapshot([{"symbol": "AAPL"}], 1.0)

    assert (tmp_path / "gappers-2026-09-04.json").exists()
    assert (tmp_path / "large_cap-2026-09-04.json").exists()
    assert cache_mod.load_large_cap_fired() == {}


def test_weekday_naming_is_unchanged(tmp_path, monkeypatch):
    _at(monkeypatch, tmp_path, "2026-09-22")  # Tuesday
    cache_mod.save_loser_snapshot([{"symbol": "BBB"}], 1.0)
    assert (tmp_path / "losers-2026-09-22.json").exists()


def test_history_menu_hides_weekend_files_left_on_disk(tmp_path, monkeypatch):
    _at(monkeypatch, tmp_path, "2026-09-22")
    _plant(tmp_path, "afterhours", "2026-09-18", [{"symbol": "A"}])  # Fri
    _plant(tmp_path, "afterhours", "2026-09-19", [{"symbol": "A"}])  # Sat
    _plant(tmp_path, "afterhours", "2026-09-20", [{"symbol": "A"}])  # Sun
    _plant(tmp_path, "large_cap", "2026-09-07", [{"symbol": "B"}])   # Labor Day

    assert cache_mod.list_history_dates("afterhours") == ["2026-09-18"]
    assert cache_mod.list_history_dates("all") == ["2026-09-18"]
    # Left on disk: nothing is deleted, only no longer offered.
    assert (tmp_path / "afterhours-2026-09-19.json").exists()


def test_hod_momo_alerts_keep_the_calendar_session_key(tmp_path, monkeypatch):
    """HOD Momo's rollover and archive paths read the calendar key; unchanged."""
    _at(monkeypatch, tmp_path, "2026-09-19")
    cache_mod.save_hod_momo_snapshot([{"symbol": "X"}], 1.0)
    assert (tmp_path / f"{cache_mod.HOD_MOMO_ALERTS_PREFIX}-2026-09-19.json").exists()


def test_retention_prunes_large_cap_snapshots_too(tmp_path, monkeypatch):
    """``large_cap-`` files were left out of the retention sweep and never pruned."""
    _at(monkeypatch, tmp_path, "2026-09-22")
    _plant(tmp_path, "large_cap", "2020-01-02", [{"symbol": "OLD"}])
    _plant(tmp_path, "gappers", "2020-01-02", [{"symbol": "OLD"}])
    cache_mod.cleanup_old_snapshots(retention_days=30)
    assert not (tmp_path / "large_cap-2020-01-02.json").exists()
    assert not (tmp_path / "gappers-2020-01-02.json").exists()
