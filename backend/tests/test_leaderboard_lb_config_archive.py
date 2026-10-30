"""The board rebuild finds Nova's archive.db without a personal path (#1068).

``lb_config.ARCHIVE_DB`` used to default to a hard-coded ``C:\\Users\\<user>\\github\\Nova\\backend\\.cache\\archive.db``:
the main checkout's archive, even from a worktree. Now: ``NOVA_ARCHIVE_DB``, else the main checkout's
``backend/.cache/archive.db`` (from a linked worktree, found through its ``.git`` pointer by ``cat_config.checkouts``,
the helper the .env lookup uses), then the worktree's own.
"""
from __future__ import annotations

import sys
from pathlib import Path

RESEARCH = Path(__file__).resolve().parents[2] / "research" / "leaderboard"
if str(RESEARCH) not in sys.path:
    sys.path.insert(0, str(RESEARCH))

import lb_config  # noqa: E402  (research/leaderboard/lb_config.py)


def _archive(checkout: Path) -> Path:
    path = checkout / "backend" / ".cache" / "archive.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def _worktree(tmp_path: Path) -> tuple[Path, Path]:
    main, wt = tmp_path / "Nova", tmp_path / "Nova-wt"
    (main / ".git" / "worktrees" / "Nova-wt").mkdir(parents=True)
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {main / '.git' / 'worktrees' / 'Nova-wt'}\n", encoding="utf-8")
    return main, wt


def test_a_main_checkout_reads_its_own_archive(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVA_ARCHIVE_DB", raising=False)
    (tmp_path / ".git").mkdir()
    own = _archive(tmp_path)
    assert lb_config.archive_db(tmp_path) == own


def test_a_worktree_reads_the_main_checkout_s_archive_before_its_own(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVA_ARCHIVE_DB", raising=False)
    main, wt = _worktree(tmp_path)
    desk = _archive(main)
    _archive(wt)                      # a backend started in the worktree leaves its own, empty one
    assert lb_config.archive_db(wt) == desk


def test_a_worktree_without_a_main_archive_reads_its_own(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVA_ARCHIVE_DB", raising=False)
    _, wt = _worktree(tmp_path)
    own = _archive(wt)
    assert lb_config.archive_db(wt) == own


def test_with_no_archive_on_disk_the_main_checkout_s_is_named(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVA_ARCHIVE_DB", raising=False)
    main, wt = _worktree(tmp_path)
    assert lb_config.archive_db(wt) == main / "backend" / ".cache" / "archive.db"


def test_nova_archive_db_comes_first(tmp_path, monkeypatch):
    explicit = tmp_path / "elsewhere" / "archive.db"
    monkeypatch.setenv("NOVA_ARCHIVE_DB", str(explicit))
    main, wt = _worktree(tmp_path)
    _archive(main)
    assert lb_config.archive_db(wt) == explicit


def test_the_rebuild_reads_the_resolved_archive():
    assert lb_config.ARCHIVE_DB == lb_config.archive_db()


def test_no_personal_path_in_the_source():
    text = Path(lb_config.__file__).read_text(encoding="utf-8")
    assert "Users\\" not in text and "Users/" not in text
