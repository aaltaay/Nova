"""The catalyst research config finds the desk .env without a personal path (#1068).

`load_env()` used to fall back to a hardcoded `C:\\Users\\<user>\\github\\Nova\\.env`. It now reads
`NOVA_ENV_PATH`, the checkout's own `.env`, and -- from a linked worktree -- the main checkout's
`.env`, found through the worktree's `.git` pointer file.
"""
from __future__ import annotations

import sys
from pathlib import Path

RESEARCH = Path(__file__).resolve().parents[2] / "research" / "catalysts"
if str(RESEARCH) not in sys.path:
    sys.path.insert(0, str(RESEARCH))

import cat_config  # noqa: E402  (research/catalysts/cat_config.py)


def test_main_checkout_reads_only_its_own_env(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVA_ENV_PATH", raising=False)
    (tmp_path / ".git").mkdir()
    assert cat_config.env_files(tmp_path) == [tmp_path / ".env"]


def test_linked_worktree_falls_back_to_the_main_checkout(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVA_ENV_PATH", raising=False)
    main, wt = tmp_path / "Nova", tmp_path / "Nova-wt"
    (main / ".git" / "worktrees" / "Nova-wt").mkdir(parents=True)
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {main / '.git' / 'worktrees' / 'Nova-wt'}\n", encoding="utf-8")
    assert cat_config.env_files(wt) == [wt / ".env", main / ".env"]


def test_nova_env_path_comes_first(tmp_path, monkeypatch):
    explicit = tmp_path / "desk.env"
    monkeypatch.setenv("NOVA_ENV_PATH", str(explicit))
    (tmp_path / ".git").mkdir()
    assert cat_config.env_files(tmp_path)[0] == explicit


def test_no_personal_path_in_the_source():
    text = Path(cat_config.__file__).read_text(encoding="utf-8")
    assert "Users\\" not in text and "Users/" not in text
