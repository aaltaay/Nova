"""Contract tests for ledger fragments and PR-derived changelog entries."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.changes_collate import pr_to_fragment, section  # noqa: E402
from tools.changes_fragments import (  # noqa: E402
    ENTRIES_MARKER,
    collate,
    load_fragments,
    parse_fragment,
    render_entry,
    render_fragment,
    slugify,
    splice_entries,
)

GITATTRIBUTES = REPO_ROOT / ".gitattributes"


def frag(**kw):
    base = dict(kind="fix", scope="capture", pr="371", title="Stop the deadlock",
                body="- **What:** it no longer deadlocks.")
    base.update(kw)
    return render_fragment(**base)


# --------------------------------------------------------------------------
# fragment round trip
# --------------------------------------------------------------------------


def test_a_fragment_round_trips():
    parsed = parse_fragment(Path("x.md"), frag())
    assert parsed.kind == "fix"
    assert parsed.scope == "capture"
    assert parsed.pr == "371"
    assert parsed.title == "Stop the deadlock"
    assert "no longer deadlocks" in parsed.body


def test_missing_front_matter_is_rejected_by_name():
    with pytest.raises(ValueError, match="x.md: missing"):
        parse_fragment(Path("x.md"), "just a body\n")


def test_an_unknown_kind_is_rejected():
    with pytest.raises(ValueError, match="not one of"):
        parse_fragment(Path("x.md"), frag(kind="wibble"))


def test_a_fragment_without_a_body_is_rejected():
    # Front matter alone would silently produce an empty changelog entry.
    with pytest.raises(ValueError, match="no body"):
        parse_fragment(Path("x.md"), frag(body=""))


def test_a_missing_title_is_rejected():
    with pytest.raises(ValueError, match="missing title"):
        parse_fragment(Path("x.md"), frag(title=""))


def test_slugify_is_filename_safe():
    assert slugify("Stop the P0 deadlock! (recorder)") == "stop-the-p0-deadlock-recorder"


# --------------------------------------------------------------------------
# splicing -- the #312 corruption must not be reproducible
# --------------------------------------------------------------------------


LEDGER = (
    "# Change log\n\nSome prose that mentions the <!-- ENTRIES_START --> marker inline.\n\n"
    f"{ENTRIES_MARKER}\n\n## 2026-01-01 — older\n\n- old\n"
)


def test_entries_land_below_the_real_marker_line_not_the_prose_mention():
    out = splice_entries(LEDGER, ["## 2026-09-20 — new\n\n- new\n"])
    body_index = out.index("## 2026-09-20")
    marker_index = out.index(f"\n{ENTRIES_MARKER}\n")
    prose_index = out.index("Some prose")
    assert prose_index < marker_index < body_index, "anchored on prose = the #312 corruption"


def test_new_entries_precede_older_ones():
    out = splice_entries(LEDGER, ["## 2026-09-20 — new\n\n- new\n"])
    assert out.index("2026-09-20") < out.index("2026-01-01")


def test_splicing_nothing_leaves_the_ledger_byte_identical():
    assert splice_entries(LEDGER, []) == LEDGER


def test_a_ledger_without_the_marker_fails_loudly():
    with pytest.raises(ValueError, match="ENTRIES_START"):
        splice_entries("# Change log\n\nno marker\n", ["## x\n"])


def test_the_real_changelog_still_has_its_marker():
    assert ENTRIES_MARKER in (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# collate
# --------------------------------------------------------------------------


def test_collate_folds_fragments_in_and_deletes_them(tmp_path):
    directory = tmp_path / "unreleased"
    directory.mkdir()
    (directory / "20260920T0101-a.md").write_text(frag(title="first"), encoding="utf-8")
    (directory / "20260920T0202-b.md").write_text(frag(title="second"), encoding="utf-8")
    ledger = tmp_path / "CHANGELOG.md"
    ledger.write_text(LEDGER, encoding="utf-8")

    count, consumed = collate(directory, ledger, date="2026-09-20")
    assert count == 2
    assert len(consumed) == 2
    assert not list(directory.glob("*.md")), "fragments must not be collated twice"
    out = ledger.read_text(encoding="utf-8")
    assert "first" in out and "second" in out


def test_collate_orders_the_newest_fragment_first(tmp_path):
    directory = tmp_path / "unreleased"
    directory.mkdir()
    (directory / "20260920T0101-a.md").write_text(frag(title="earlier"), encoding="utf-8")
    (directory / "20260920T0202-b.md").write_text(frag(title="later"), encoding="utf-8")
    ledger = tmp_path / "CHANGELOG.md"
    ledger.write_text(LEDGER, encoding="utf-8")
    collate(directory, ledger, date="2026-09-20")
    out = ledger.read_text(encoding="utf-8")
    assert out.index("later") < out.index("earlier")


def test_collate_on_an_empty_directory_is_a_quiet_no_op(tmp_path):
    ledger = tmp_path / "CHANGELOG.md"
    ledger.write_text(LEDGER, encoding="utf-8")
    assert collate(tmp_path / "nope", ledger, date="2026-09-20") == (0, [])
    assert ledger.read_text(encoding="utf-8") == LEDGER


def test_load_fragments_on_a_missing_directory_returns_nothing(tmp_path):
    assert load_fragments(tmp_path / "absent") == []


# --------------------------------------------------------------------------
# PR-derived entries -- the agent writes nothing
# --------------------------------------------------------------------------


PR_BODY = """## What

Fixed the recorder stop deadlock.

## Why this approach

A reentrant lock would have hidden the reentry instead of removing it.

## Verified by

`pytest backend/tests/test_capture.py` -> 12 passed.

🤖 Generated with Claude Code
"""


def test_section_extracts_one_heading_only():
    assert section(PR_BODY, "What") == "Fixed the recorder stop deadlock."
    assert "reentrant" in section(PR_BODY, "Why this approach")


def test_section_is_empty_for_an_absent_heading():
    assert section(PR_BODY, "Screenshots") == ""


def test_a_pr_becomes_a_ledger_entry_without_any_fragment_file():
    fragment = pr_to_fragment({"number": 371, "title": "fix(capture): stop deadlock", "body": PR_BODY})
    assert fragment is not None
    assert fragment.pr == "371"
    assert fragment.kind == "fix"
    assert "**What:**" in fragment.body
    assert "**Why this approach:**" in fragment.body
    assert "**Verified by:**" in fragment.body


def test_the_attribution_footer_stays_out_of_the_ledger():
    fragment = pr_to_fragment({"number": 371, "title": "fix: x", "body": PR_BODY})
    assert "Generated with" not in fragment.body


def test_a_pr_with_no_what_section_produces_nothing():
    # Bot merges and pure-chore PRs would otherwise pad the ledger with noise.
    assert pr_to_fragment({"number": 9, "title": "chore: bump", "body": "no headings here"}) is None


def test_an_unrecognised_title_prefix_falls_back_to_chore():
    fragment = pr_to_fragment({"number": 9, "title": "wibble: x", "body": PR_BODY})
    assert fragment.kind == "chore"


def test_a_pr_entry_links_back_to_the_pull_request():
    fragment = pr_to_fragment({"number": 371, "title": "fix: x", "body": PR_BODY})
    assert "/pull/371" in render_entry(fragment, date="2026-09-20")


# --------------------------------------------------------------------------
# the transitional net
# --------------------------------------------------------------------------


def test_union_merge_covers_the_hand_written_ledgers():
    # In-flight PRs were authored before the ledger became generated; union
    # merging keeps both sides instead of blocking on a paperwork conflict.
    text = GITATTRIBUTES.read_text(encoding="utf-8")
    for ledger in ("CHANGELOG.md", "PROBLEM_LOG.md", "knowledge/task-log/INDEX.md"):
        assert f"{ledger}" in text
    assert "merge=union" in text


def test_union_merge_is_documented_as_transitional():
    text = GITATTRIBUTES.read_text(encoding="utf-8")
    assert "transitional" in text.lower(), "a permanent union merge would hide real conflicts"


def test_a_coauthor_trailer_also_stays_out():
    body = PR_BODY.replace("🤖 Generated with Claude Code",
                           "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>")
    fragment = pr_to_fragment({"number": 371, "title": "fix: x", "body": body})
    assert "Co-Authored-By" not in fragment.body


def test_a_trailer_does_not_truncate_an_earlier_section():
    assert section(PR_BODY, "What") == "Fixed the recorder stop deadlock."


def test_the_watermark_stops_a_rerun_duplicating_entries(tmp_path, monkeypatch):
    import tools.changes_collate as cc
    mark = tmp_path / "last-collated"
    monkeypatch.setattr(cc, "WATERMARK", mark)
    assert cc.read_watermark() is None, "absent watermark must not crash the first run"
    cc.write_watermark(371)
    assert cc.read_watermark() == 371


def test_a_corrupt_watermark_is_treated_as_absent(tmp_path, monkeypatch):
    import tools.changes_collate as cc
    mark = tmp_path / "last-collated"
    mark.write_text("not a number\n", encoding="utf-8")
    monkeypatch.setattr(cc, "WATERMARK", mark)
    assert cc.read_watermark() is None
