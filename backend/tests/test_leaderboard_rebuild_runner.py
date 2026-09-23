"""The unattended five-year rebuild (ADR 023): resumable, and never inside the desk's session."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from tests.test_leaderboard_reconstruct_helpers import session  # noqa: F401  (puts research/leaderboard on sys.path)

import build_leaderboard  # noqa: E402
from leaderboard import store  # noqa: E402

ET = ZoneInfo("America/New_York")


def test_it_never_builds_inside_the_desks_session():
    tuesday = lambda h, m: datetime(2026, 9, 22, h, m, tzinfo=ET)  # noqa: E731
    assert build_leaderboard.in_desk_session(tuesday(3, 45))
    assert build_leaderboard.in_desk_session(tuesday(12, 0))
    assert build_leaderboard.in_desk_session(tuesday(20, 4))
    assert not build_leaderboard.in_desk_session(tuesday(20, 5))
    assert not build_leaderboard.in_desk_session(tuesday(3, 44))
    assert not build_leaderboard.in_desk_session(datetime(2026, 9, 19, 12, 0, tzinfo=ET))  # Saturday


def test_only_a_day_covering_every_minute_counts_as_complete(tmp_path):
    db_path = tmp_path / "lb.sqlite3"

    def coverage(day: str, minutes: int) -> list[dict]:
        base = int(datetime.fromisoformat(f"{day}T04:01:00-04:00").timestamp())
        return [{"session_date": day, "minute_ts": base + 60 * i, "source": "reconstructed", "board": "market",
                 "state": "rebuilt", "row_count": 0, "run_id": None} for i in range(minutes)]

    with store.connect(db_path) as db:
        store.write_batch(db, coverage=coverage("2026-09-17", 960) + coverage("2026-09-18", 420))
    assert build_leaderboard.complete_days(db_path) == {"2026-09-17"}


def test_chunks_bound_each_load():
    days = list(range(45))
    assert [len(c) for c in build_leaderboard._chunks(days, 20)] == [20, 20, 5]
