"""Fidelity tests: exported transcripts must match raw Wistia caption JSON exactly.

These tests prove no LLM rewriting/hallucination occurred: every word in each
exported Markdown transcript must be the concatenation of the official caption
cues, and every timestamp must map to a real cue start time.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from constants import DEFAULT_CAPTION_EXPORT_ROOT

CACHE = DEFAULT_CAPTION_EXPORT_ROOT / "_caption_cache"
ROW_RE = re.compile(r"^- (\d{2}):(\d{2}):(\d{2}) — (.+)$")


def _english_lines(media_id: str) -> list[dict]:
    data = json.loads((CACHE / f"{media_id}.captions.json").read_text(encoding="utf-8"))
    captions = data.get("captions") or []
    for cap in captions:
        code = str(cap.get("wistiaLanguageCode", "")).lower()
        name = str(cap.get("name", "")).lower()
        if code.startswith("eng") or name.startswith("english"):
            return (cap.get("hash") or {}).get("lines") or []
    return (captions[0].get("hash") or {}).get("lines") or [] if captions else []


def _cue_text(line: dict) -> str:
    text = line.get("text") or []
    if isinstance(text, list):
        return " ".join(str(t) for t in text).strip()
    return str(text).strip()


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _official_transcripts() -> list[Path]:
    if not DEFAULT_CAPTION_EXPORT_ROOT.exists():
        return []
    found = []
    for path in sorted(DEFAULT_CAPTION_EXPORT_ROOT.rglob("*.md")):
        if path.name.startswith("_") or path.name.upper() == "COURSE_INVENTORY.MD":
            continue
        head = path.read_text(encoding="utf-8")[:400]
        if "source: warrior-trading-official-captions" in head:
            found.append(path)
    return found


TRANSCRIPTS = _official_transcripts()


@pytest.mark.skipif(not TRANSCRIPTS, reason="no official transcripts on this machine")
@pytest.mark.parametrize("md_path", TRANSCRIPTS, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_transcript_text_matches_raw_captions_exactly(md_path: Path) -> None:
    body = md_path.read_text(encoding="utf-8")
    media_id = re.search(r"^media_id: (\w+)$", body, re.MULTILINE)
    assert media_id, f"{md_path} missing media_id"
    lines = _english_lines(media_id.group(1))
    assert lines, f"no cached captions for {media_id.group(1)}"

    # Full transcript text from the MD rows must equal full raw caption text.
    md_rows = [m.group(4) for m in map(ROW_RE.match, body.splitlines()) if m]
    assert md_rows, f"{md_path} has no transcript rows"
    md_text = _normalize(" ".join(md_rows))
    raw_text = _normalize(" ".join(_cue_text(line) for line in lines if _cue_text(line)))
    assert md_text == raw_text, (
        f"{md_path.name}: transcript text diverges from official captions "
        f"(md {len(md_text)} chars vs raw {len(raw_text)} chars)"
    )


@pytest.mark.skipif(not TRANSCRIPTS, reason="no official transcripts on this machine")
@pytest.mark.parametrize("md_path", TRANSCRIPTS, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_transcript_timestamps_map_to_real_cue_starts(md_path: Path) -> None:
    body = md_path.read_text(encoding="utf-8")
    media_id = re.search(r"^media_id: (\w+)$", body, re.MULTILINE).group(1)
    valid_starts = {int(float(line.get("start") or 0)) for line in _english_lines(media_id)}

    for match in filter(None, map(ROW_RE.match, body.splitlines())):
        h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
        assert h * 3600 + m * 60 + s in valid_starts, (
            f"{md_path.name}: timestamp {match.group(1)}:{match.group(2)}:{match.group(3)} "
            "does not correspond to any real caption cue"
        )


@pytest.mark.skipif(not TRANSCRIPTS, reason="no official transcripts on this machine")
def test_no_paraphrase_files_remain_in_official_folders() -> None:
    for path in DEFAULT_CAPTION_EXPORT_ROOT.rglob("*.md"):
        if path.name.startswith("_") or path.name.upper() == "COURSE_INVENTORY.MD":
            continue
        head = path.read_text(encoding="utf-8")[:400]
        assert "minute-by-minute-paraphrase" not in head, (
            f"{path} is still a paraphrase file — must be regenerated from captions"
        )
        assert "density: official-caption-transcript" in head or "source: whisper-local-audio" in head, (
            f"{path} has unknown provenance"
        )
