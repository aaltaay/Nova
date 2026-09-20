"""Retired ledgers must not be required or recreated by agent automation."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RETIRED = ("CHANGELOG.md", "PROBLEM_LOG.md", "BACKLOG.md")


def test_retired_ledgers_are_absent_from_the_repo_root():
    for name in RETIRED:
        assert not (REPO_ROOT / name).exists(), f"{name} was recreated"


def test_retired_ledgers_are_readable_in_the_archive():
    archive = REPO_ROOT / "_archived" / "agent-ledgers-2026-09-20"
    for name in RETIRED:
        snapshot = archive / name
        assert snapshot.is_file(), f"{name} history was lost, not archived"
        assert snapshot.read_text(encoding="utf-8").startswith("> ARCHIVED"), name


def test_changelog_generation_machinery_is_gone():
    """The generator is retired with the file; a half-removal would resurrect it."""
    for rel in (
        ".github/workflows/ledger-collate.yml",
        "tools/changes_collate.py",
        "tools/changes_fragments.py",
        "tools/changes_new.py",
        ".changes",
        ".cursor/rules/change-log.mdc",
    ):
        assert not (REPO_ROOT / rel).exists(), f"{rel} still present"


def test_union_merge_attribute_was_dropped_with_the_ledger():
    """merge=union only existed to stop changelog paperwork conflicting (#344)."""
    attributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "CHANGELOG.md" not in attributes


def test_active_agent_prompts_do_not_require_a_retired_ledger():
    for path in (REPO_ROOT / ".cursor" / "agents").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for token in ("problem_log=", "PROBLEM_LOG", "CHANGELOG"):
            assert token not in text, f"{path.name} still requires {token}"
    assert not (REPO_ROOT / ".cursor/rules/problem-log.mdc").exists()


def test_rules_do_not_ask_for_a_changelog_entry():
    """A rule is read every request; a stale one re-imposes the ledger.

    Naming the file to forbid recreating it is correct, so this looks for
    requirement-shaped phrasing rather than any mention.
    """
    demands = (
        "Update `CHANGELOG",
        "CHANGELOG entry",
        "CHANGELOG is generated",
        "changes_new.py",
        "ledger-collate",
    )
    for path in (REPO_ROOT / ".cursor" / "rules").glob("*.mdc"):
        text = path.read_text(encoding="utf-8")
        for demand in demands:
            assert demand not in text, f"{path.name} still demands: {demand}"
