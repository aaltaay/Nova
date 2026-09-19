"""Tests for tools/doc_invariants.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "tools" / "doc_invariants.py"


def _load():
    spec = importlib.util.spec_from_file_location("doc_invariants", MODULE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["doc_invariants"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def di():
    return _load()


def test_current_repo_passes(di):
    violations = di.run_scan(REPO_ROOT)
    assert violations == [], [
        f"{v.path}:{v.line} [{v.invariant_id}] {v.snippet}" for v in violations
    ]


def test_detects_railway_deploy_claim(di):
    text = "The API is deployed to Railway on every push.\n"
    hits = di.scan_text(Path("AGENTS.md"), text)
    assert any(h.invariant_id == "railway_deployed" for h in hits)


def test_allows_railway_retirement_wording(di):
    text = "Backend is local only -- no cloud host (not Railway, not another PaaS).\n"
    hits = di.scan_text(Path("AGENTS.md"), text)
    assert hits == []


def test_detects_absolute_no_trades(di):
    text = "Stock alert system (read-only market data; does not execute trades).\n"
    hits = di.scan_text(Path("README.md"), text)
    assert any(h.invariant_id == "absolute_no_trades" for h in hits)


def test_detects_discovery_alpaca_instruction(di):
    text = "2. Confirm IB Gateway is disconnected or use discovery=alpaca mode\n"
    hits = di.scan_text(Path("security/tooling.md"), text)
    assert any(h.invariant_id == "discovery_alpaca_mode" for h in hits)


def test_detects_nova_public_as_source(di):
    text = "Clone https://github.com/aaltaay/Nova-public and run the desk.\n"
    hits = di.scan_text(Path("README.md"), text)
    assert any(h.invariant_id == "nova_public_as_source" for h in hits)


def test_allows_nova_public_archive_wording(di):
    text = "The older `Nova-public` repository is a private archive.\n"
    hits = di.scan_text(Path("README.md"), text)
    assert hits == []


def test_missing_live_path_is_a_violation(di, tmp_path, monkeypatch):
    """A renamed/deleted live doc must fail loudly, not shrink coverage in silence."""
    (tmp_path / "AGENTS.md").write_text("all good\n", encoding="utf-8")
    monkeypatch.setattr(di, "LIVE_PATHS", ("AGENTS.md", "docs/gone.md"))
    monkeypatch.setattr(di, "LIVE_GLOBS", ())
    violations = di.run_scan(tmp_path)
    assert [v.invariant_id for v in violations] == ["missing_live_path"]
    assert violations[0].path == "docs/gone.md"


def test_missing_live_path_exits_nonzero(di, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(di, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(di, "LIVE_PATHS", ("docs/gone.md",))
    monkeypatch.setattr(di, "LIVE_GLOBS", ())
    assert di.main([]) == 1
    assert "missing_live_path" in capsys.readouterr().err


def test_live_globs_may_match_nothing(di, tmp_path, monkeypatch):
    """A glob legitimately matches zero files; only explicit paths are asserted."""
    monkeypatch.setattr(di, "LIVE_PATHS", ())
    monkeypatch.setattr(di, "LIVE_GLOBS", ("nowhere/*.mdc",))
    assert di.run_scan(tmp_path) == []


def test_main_exits_nonzero_on_violation(di, tmp_path, monkeypatch, capsys):
    live = tmp_path / "AGENTS.md"
    live.write_text("Deploy to Railway now.\n", encoding="utf-8")
    monkeypatch.setattr(di, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(di, "LIVE_PATHS", ("AGENTS.md",))
    monkeypatch.setattr(di, "LIVE_GLOBS", ())
    code = di.main([])
    assert code == 1
    err = capsys.readouterr().err
    assert "railway_deploy_job" in err


# --- agent-maintained entry logs (CHANGELOG.md / PROBLEM_LOG.md) -------------
#
# Regression cover for the first-match prepend: four commits (bd0d0cb6,
# e4a73ef9, 5854569, 58f6bc7) anchored on the how-to's prose mention of the
# marker instead of the standalone marker line.

HOWTO_TAIL = "` marker (newest entries at the top)."
STEP_TWO = (
    "2. **Where:** Prepend a new `##` section **immediately below** the "
    "`<!-- ENTRIES_START -->" + HOWTO_TAIL
)


def _entry_log(step_two: str = STEP_TWO, above: str = "", entries: str = "") -> str:
    """A minimal but faithful CHANGELOG.md shape."""
    return (
        f"{above}# Change log (agent-maintained)\n"
        "\n"
        "## How agents update this file\n"
        "\n"
        "1. **When:** After completing any task.\n"
        f"{step_two}\n"
        "3. **Commit together:** Ships in the same commit.\n"
        "\n"
        "```markdown\n"
        "## YYYY-MM-DD — Short descriptive title\n"
        "```\n"
        "\n"
        "<!-- ENTRIES_START -->\n"
        "\n"
        f"{entries}"
        "## 2026-09-01 -- An older entry\n"
        "\n"
        "- **What:** something.\n"
    )


def _check(di, text):
    return [v.invariant_id for v in di.check_entry_log("CHANGELOG.md", "# Change log (agent-maintained)", text)]


def test_entry_log_accepts_a_healthy_file(di):
    assert _check(di, _entry_log()) == []


def test_entry_log_flags_entry_wedged_into_the_how_to(di):
    """The exact bd0d0cb6 shape: step 2 split, entry inside the instructions."""
    split = (
        "2. **Where:** Prepend a new `##` section **immediately below** the "
        "`<!-- ENTRIES_START -->\n"
        "\n"
        "## 2026-09-19 -- Sim pause/play button\n"
        "\n"
        "- **What:** a button.\n" + HOWTO_TAIL
    )
    ids = _check(di, _entry_log(step_two=split))
    assert "entry_log_entry_above_marker" in ids
    assert "entry_log_howto_split" in ids


def test_entry_log_flags_block_above_the_title(di):
    """The 8745b964 shape: an '## Unreleased' block prepended above the H1."""
    above = "## Unreleased\n\n### Fixed\n- **Sim tape charts:** fixed.\n"
    ids = _check(di, _entry_log(above=above))
    assert "entry_log_title" in ids
    assert "entry_log_entry_above_marker" in ids


def test_entry_log_flags_a_missing_or_duplicated_marker(di):
    text = _entry_log()
    assert _check(di, text.replace("<!-- ENTRIES_START -->\n\n", "", 1)) == ["entry_log_marker"]
    doubled = text.replace(
        "<!-- ENTRIES_START -->\n\n", "<!-- ENTRIES_START -->\n\n<!-- ENTRIES_START -->\n\n", 1
    )
    assert _check(di, doubled) == ["entry_log_marker"]


def test_entry_log_allows_the_template_heading_above_the_marker(di):
    """'## YYYY-MM-DD — Short descriptive title' lives in the how-to fence."""
    assert "entry_log_entry_above_marker" not in _check(di, _entry_log())


def test_entry_logs_skip_absent_files(di, tmp_path):
    """Other tests scan tmp roots; absent logs must not manufacture violations."""
    assert di.check_entry_logs(tmp_path) == []


def test_real_repo_entry_logs_are_present_and_structurally_sound(di):
    for rel, _title in di.ENTRY_LOGS:
        assert (REPO_ROOT / rel).is_file(), f"{rel} missing -- gate lost coverage"
    assert di.check_entry_logs(REPO_ROOT) == []
