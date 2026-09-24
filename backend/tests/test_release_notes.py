"""Tests for tools/release_notes.py: the Release body the desk reads its notes from."""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "tools" / "release_notes.py"


def _load():
    spec = importlib.util.spec_from_file_location("release_notes", TOOL)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


rn = _load()

SQUASH = """fix(sim): Session Record replays draw candles from their prints

## What

A Session Record replay now draws every candle from its recorded prints (#535, operator decision: option a). Recordings made before stored buckets built from **every** print.

## Why this approach

- **One path for every recording.** Not for the operator.

## Verified by

- pytest -> 565 passed
"""


def _record(body: str) -> dict:
    match = re.search(r"<!-- nova-release-notes (\{.*?\}) -->", body)
    assert match, body
    return json.loads(match.group(1))


def test_record_is_the_subject_and_the_first_what_paragraph() -> None:
    record = rn.notes_record("v975", SQUASH, 539)
    assert record == {
        "schema_version": 1,
        "tag": "v975",
        "title": "Session Record replays draw candles from their prints",
        "kind": "fix",
        "scope": "sim",
        "pr": 539,
        "summary": "A Session Record replay now draws every candle from its recorded prints. "
        "Recordings made before stored buckets built from every print.",
        "points": [],
    }


def test_body_carries_readable_notes_the_record_and_the_installer_text() -> None:
    body = rn.release_body("v975", SQUASH, 539)
    assert body.startswith("## What's new in v975\n\n**Session Record replays draw candles from their prints**")
    assert "fix · sim · #539" in body
    assert _record(body)["summary"].startswith("A Session Record replay")
    assert "Nova v975 Windows desktop." in body
    assert "Nova-Setup-v975.exe" in body
    # Engineering sections never reach the operator.
    assert "One path for every recording" not in body
    assert "565 passed" not in body


def test_skips_operator_quotes_and_takes_a_list_the_summary_introduces() -> None:
    message = """feat(ticket): Bid / Mid / Ask keep the limit on the live book

## What

Operator report: pressing Ask set the limit once.

Now clicking **Bid**, **Mid** or **Ask** keeps the limit on that side. Following stops when the operator:

- types a price,
- clicks the lit button again (the price stays where it is), or
- changes symbol.
"""
    summary, points = rn.operator_summary(message)
    assert summary.startswith("Now clicking Bid, Mid or Ask keeps the limit")
    assert points == ["types a price", "clicks the lit button again (the price stays where it is), or", "changes symbol"]


def test_takes_bold_lead_ins_and_drops_engineering_bullets() -> None:
    leads = """feat(trader): Focus list sorts

## What

The Focus list works like a table you can sort (operator ask: "sort it").

- **Sort by any column.** Headers sort the list.
- **Hover cards.** Hovering explains the dots.
- Sim away from the live edge still hides today's price.
"""
    summary, points = rn.operator_summary(leads)
    assert summary == "The Focus list works like a table you can sort."
    assert points == ["Sort by any column", "Hover cards"]

    files = """feat(brand): A Nova icon

## What

Nova gets its own icon.

- `frontend/electron/build/icon.svg` is the source.
- `npm run icons` rasterises each size.
"""
    assert rn.operator_summary(files) == ("Nova gets its own icon.", [])


def test_a_direct_push_without_the_template_uses_its_commit_body() -> None:
    message = "chore: bump pins\n\nPins electron to 39.8.10 for the updater fix.\n"
    record = rn.notes_record("v980", message)
    assert record["kind"] == "chore"
    assert record["scope"] is None
    assert record["summary"] == "Pins electron to 39.8.10 for the updater fix."
    assert rn.notes_record("v981", "Merge something")["title"] == "Merge something"


def test_the_record_can_never_close_its_comment() -> None:
    message = "fix: arrows\n\n## What\n\nA --> B and <script>x</script> stay text.\n"
    line = rn.marker_line(rn.notes_record("v982", message))
    inner = line[len("<!-- ") : -len(" -->")]
    assert "-->" not in inner and "<" not in inner and ">" not in inner
    assert json.loads(inner.split(" ", 1)[1])["summary"] == "A --> B and x stay text."


def test_long_text_is_cut_at_a_sentence() -> None:
    long = "Short first sentence here. " + "word " * 200
    assert rn.clip(long, 50) == "Short first sentence here."
    # A sentence end too early to keep half the room is not used.
    assert rn.clip(long, 60).endswith("…")
    assert rn.clip("x" * 80, 20).endswith("…")


def test_refuses_anything_but_a_release_tag() -> None:
    with pytest.raises(ValueError):
        rn.release_body("975", SQUASH)


def test_cli_prints_utf8_body(tmp_path: Path) -> None:
    msg = tmp_path / "msg.txt"
    msg.write_text(SQUASH, encoding="utf-8")
    out = subprocess.run(
        [sys.executable, str(TOOL), "body", "--tag", "v975", "--message-file", str(msg), "--pr", "539"],
        capture_output=True,
        check=True,
    )
    text = out.stdout.decode("utf-8")
    assert "fix · sim · #539" in text
    assert _record(text)["pr"] == 539
