"""Parse Nova agent memory files into staged dream candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

SECTION_RE = re.compile(r"^## (.+)$", re.MULTILINE)
SNAPSHOT_RE = re.compile(
    r"## Current snapshot\s*\n+```ya?ml\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)
RUN_LOG_RE = re.compile(
    r"(<!-- RUN_LOG_START -->)(.*?)(<!-- RUN_LOG_END -->)",
    re.DOTALL,
)
LEARNING_RE = re.compile(r"^\s*-\s*\*\*Learning:\*\*\s*(.+)$", re.MULTILINE)
WIP_RE = re.compile(r"\bWIP\b|\buntracked\b|\bthis session\b", re.IGNORECASE)

MIN_FACT_LEN = 40
MAX_FACT_LEN = 400
RUN_LOG_CAP = 30


@dataclass
class PendingFact:
    text: str
    raw_line: str


@dataclass
class AgentMemory:
    agent_id: str
    memory_path: Path
    spec_path: Path
    text: str
    snapshot_block: str | None = None
    open_backlog: list[str] = field(default_factory=list)
    pending_facts: list[PendingFact] = field(default_factory=list)
    run_log_entries: list[str] = field(default_factory=list)
    learnings: list[str] = field(default_factory=list)


def _section_body(text: str, title: str) -> str | None:
    matches = list(SECTION_RE.finditer(text))
    for i, m in enumerate(matches):
        if m.group(1).strip().lower() == title.lower():
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[start:end]
    return None


def _parse_pending(body: str) -> list[PendingFact]:
    if not body or "(empty)" in body.lower():
        return []
    facts: list[PendingFact] = []
    # Stop at nested headings inside the section (none expected) or Completed bleed.
    for raw in body.splitlines():
        line = raw.rstrip()
        if not line.startswith("- "):
            continue
        if line.startswith("- [") or line.startswith("- [x]") or line.startswith("- [ ]"):
            continue
        content = line[2:].strip()
        if not content or content.lower() == "(empty)":
            continue
        facts.append(PendingFact(text=content, raw_line=line))
    return facts


def _parse_open_backlog(body: str) -> list[str]:
    if not body:
        return []
    # Only the open list before ### Completed
    cut = re.split(r"^### Completed\s*$", body, maxsplit=1, flags=re.MULTILINE)[0]
    items: list[str] = []
    for raw in cut.splitlines():
        line = raw.strip()
        if line.startswith("- [ ]"):
            items.append(line[5:].strip())
    return items


def _parse_run_log_entries(text: str) -> list[str]:
    m = RUN_LOG_RE.search(text)
    if not m:
        # Fallback: ### dated headings under Run log
        body = _section_body(text, "Run log") or ""
        parts = re.split(r"(?=^### )", body, flags=re.MULTILINE)
        return [p.strip() for p in parts if p.strip().startswith("### ")]
    inner = m.group(2)
    parts = re.split(r"(?=^### )", inner, flags=re.MULTILINE)
    return [p.strip() for p in parts if p.strip().startswith("### ")]


def load_agent_memory(
    agent_id: str,
    memory_path: Path,
    spec_path: Path,
) -> AgentMemory:
    text = memory_path.read_text(encoding="utf-8") if memory_path.is_file() else ""
    snap_m = SNAPSHOT_RE.search(text)
    pending_body = _section_body(text, "Learned facts (pending promotion)") or ""
    backlog_body = _section_body(text, "Backlog") or ""
    entries = _parse_run_log_entries(text)
    learnings = [m.group(1).strip() for m in LEARNING_RE.finditer(text)]
    return AgentMemory(
        agent_id=agent_id,
        memory_path=memory_path,
        spec_path=spec_path,
        text=text,
        snapshot_block=snap_m.group(1) if snap_m else None,
        open_backlog=_parse_open_backlog(backlog_body),
        pending_facts=_parse_pending(pending_body),
        run_log_entries=entries,
        learnings=learnings,
    )


def _normalize_for_match(text: str) -> str:
    t = text.lower()
    t = re.sub(r"[*_`#]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_promotable(fact: PendingFact, spec_text: str) -> tuple[bool, str]:
    t = fact.text.strip()
    if WIP_RE.search(t):
        return False, "wip_reject"
    if len(t) < MIN_FACT_LEN:
        return False, "too_short"
    if len(t) > MAX_FACT_LEN:
        return False, "too_long"
    # Near-substring dupe check (ignore markdown emphasis / whitespace)
    norm = _normalize_for_match(t)
    needle = norm[:80] if len(norm) >= 80 else norm
    spec_norm = _normalize_for_match(spec_text)
    if needle and needle in spec_norm:
        return False, "already_in_spec"
    return True, "ok"


def trim_run_log_text(text: str, cap: int = RUN_LOG_CAP) -> tuple[str, int]:
    """Keep newest ``cap`` run-log entries. Returns (new_text, removed_count)."""
    m = RUN_LOG_RE.search(text)
    if not m:
        return text, 0
    entries = _parse_run_log_entries(text)
    if len(entries) <= cap:
        return text, 0
    kept = entries[:cap]
    removed = len(entries) - cap
    new_inner = "\n\n" + "\n\n".join(kept) + "\n\n"
    new_text = text[: m.start(2)] + new_inner + text[m.end(2) :]
    return new_text, removed


def remove_pending_facts(text: str, raw_lines: list[str]) -> str:
    if not raw_lines:
        return text
    body = _section_body(text, "Learned facts (pending promotion)")
    if body is None:
        return text
    # Rebuild section with remaining bullets
    matches = list(SECTION_RE.finditer(text))
    start = end = None
    for i, m in enumerate(matches):
        if m.group(1).strip().lower() == "learned facts (pending promotion)":
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            break
    if start is None or end is None:
        return text
    section = text[start:end]
    lines_out: list[str] = []
    remove_set = {ln.rstrip() for ln in raw_lines}
    for line in section.splitlines():
        if line.rstrip() in remove_set:
            continue
        lines_out.append(line)
    # Ensure section still has content hint if empty of bullets
    rebuilt = "\n".join(lines_out)
    if not any(ln.startswith("- ") for ln in lines_out):
        # Insert (empty) after intro paragraphs
        if "(empty)" not in rebuilt.lower():
            rebuilt = rebuilt.rstrip() + "\n\n**(empty)**\n"
    return text[:start] + rebuilt + ("\n" if not rebuilt.endswith("\n") else "") + text[end:]


def append_promotion_to_spec(spec_text: str, fact_text: str, agent_id: str) -> str:
    """Append a durable bullet under Known traps or Dream promotions."""
    bullet = f"- {fact_text.strip()}"
    if re.search(r"^## Known traps\s*$", spec_text, re.MULTILINE | re.IGNORECASE):
        # Insert after heading line
        def _ins(m: re.Match[str]) -> str:
            return m.group(0) + f"\n\n{bullet}"

        return re.sub(
            r"^## Known traps\s*$",
            _ins,
            spec_text,
            count=1,
            flags=re.MULTILINE | re.IGNORECASE,
        )
    # Create Dream promotions section before Invoke phrases if present
    block = (
        f"\n## Dream promotions\n\n"
        f"Durable facts promoted by `tools/agent_dream.py` for `{agent_id}`.\n\n"
        f"{bullet}\n"
    )
    inv = re.search(r"^## Invoke phrases\s*$", spec_text, re.MULTILINE)
    if inv:
        return spec_text[: inv.start()] + block + "\n" + spec_text[inv.start() :]
    return spec_text.rstrip() + "\n" + block


def stamp_last_dream(text: str, when: str) -> str:
    """Add/update last_dream_at inside snapshot notes field."""
    m = SNAPSHOT_RE.search(text)
    if not m:
        return text
    block = m.group(1)
    stamp = f"last_dream_at={when}"

    def _replace_notes(mm: re.Match[str]) -> str:
        raw = mm.group(1).strip().strip("\"'")
        if "last_dream_at=" in raw:
            cleaned = re.sub(r"last_dream_at=[^;]*;?\s*", "", raw).strip(" ;")
            rest = f"; {cleaned}" if cleaned else ""
            return f'notes: "{stamp}{rest}"'
        if not raw:
            return f'notes: "{stamp}"'
        return f'notes: "{stamp}; {raw}"'

    if re.search(r"^notes:", block, re.MULTILINE):
        new_block = re.sub(
            r"^notes:\s*(.*)$",
            _replace_notes,
            block,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        new_block = block.rstrip() + f'\nnotes: "{stamp}"\n'
    return text[: m.start(1)] + new_block + text[m.end(1) :]
