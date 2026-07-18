"""Tests for Nova agent dreaming (light / REM / deep)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from agent_dream_lib.parse import (  # noqa: E402
    append_promotion_to_spec,
    is_promotable,
    load_agent_memory,
    trim_run_log_text,
)
from agent_dream_lib.phases import run_dream  # noqa: E402
from agent_dream_lib.parse import PendingFact  # noqa: E402

MEMORY_TMPL = """# Demo memory (living)

## Current snapshot

```yaml
captured_at: 2026-07-18T00:00:00-04:00
source_revision: abc1234
result: clean
metrics: {{}}
blockers: []
dashboard_freshness: clean
notes: "seed"
```

## Backlog

- [ ] Expand routing table for news modules once touched often enough.
- [x] Done item stays put

### Completed

- [x] 2026-07-01 — Seed

## Learned facts (pending promotion)

{pending}

## Run log

Newest first.

<!-- RUN_LOG_START -->

{run_log}

<!-- RUN_LOG_END -->
"""

SPEC_TMPL = """# Demo agent

## Known traps

- Existing trap about pytest paths on Windows.

## Invoke phrases

- "Use the demo subagent"
"""


def _entry(n: int) -> str:
    return (
        f"### 2026-07-{n:02d} — Run {n}\n\n"
        f"- **Scope:** test\n"
        f"- **Result:** PASS\n"
        f"- **Learning:** Prefer fresh browser open for layout claims on run {n}.\n"
    )


def _write_agent(root: Path, agent_id: str, *, pending: str, run_count: int) -> dict:
    mem = root / ".cursor" / "agent-memory" / f"{agent_id}-memory.md"
    spec = root / ".cursor" / "agents" / f"{agent_id}.md"
    mem.parent.mkdir(parents=True, exist_ok=True)
    spec.parent.mkdir(parents=True, exist_ok=True)
    run_log = "\n".join(_entry(i) for i in range(run_count, 0, -1))
    mem.write_text(
        MEMORY_TMPL.format(pending=pending, run_log=run_log),
        encoding="utf-8",
    )
    spec.write_text(SPEC_TMPL, encoding="utf-8")
    return {
        "id": agent_id,
        "name": agent_id,
        "spec": f".cursor/agents/{agent_id}.md",
        "memory": f".cursor/agent-memory/{agent_id}-memory.md",
    }


@pytest.fixture
def dream_root(tmp_path: Path) -> Path:
    reg = {"agents": []}
    (tmp_path / ".cursor" / "agent-system").mkdir(parents=True)
    (tmp_path / ".cursor" / "agent-system" / "registry.json").write_text(
        json.dumps(reg), encoding="utf-8"
    )
    return tmp_path


def test_is_promotable_rejects_wip_and_short():
    ok, reason = is_promotable(
        PendingFact("WIP note about untracked stock view", "- WIP note"),
        "",
    )
    assert not ok and reason == "wip_reject"
    ok2, reason2 = is_promotable(PendingFact("too short", "- too short"), "")
    assert not ok2 and reason2 == "too_short"


def test_is_promotable_skips_dupe_in_spec():
    fact = PendingFact(
        "**agent-browser download:** download Export often cancels in headless; prove via unit tests.",
        "- **agent-browser download:** download Export often cancels in headless; prove via unit tests.",
    )
    spec = "Something about agent-browser download: download Export often cancels in headless; prove via unit tests. more"
    ok, reason = is_promotable(fact, spec)
    assert not ok and reason == "already_in_spec"


def test_trim_run_log_keeps_newest_30():
    entries = "\n\n".join(_entry(i) for i in range(35, 0, -1))
    text = (
        "pre\n<!-- RUN_LOG_START -->\n\n" + entries + "\n\n<!-- RUN_LOG_END -->\npost"
    )
    new, removed = trim_run_log_text(text, cap=30)
    assert removed == 5
    assert new.count("### 2026-07-") == 30
    assert "### 2026-07-35" in new
    assert "### 2026-07-01 — Run 1" not in new


def test_light_stages_promotable(dream_root: Path):
    pending = (
        "- **agent-browser download:** download @Export often cancels in headless; "
        "prove export via serializeHtk unit tests when file capture fails.\n"
        "- short\n"
        "- WIP note about untracked directory should not promote into the agent prompt.\n"
    )
    entry = _write_agent(dream_root, "demo", pending=pending, run_count=3)
    registry = {"agents": [entry]}
    report = run_dream(
        registry,
        dream_root,
        phase="light",
        write=False,
        diary_path=dream_root / "DREAMS.md",
    )
    assert len(report.agents) == 1
    assert report.agents[0].pending_count == 3
    assert len(report.agents[0].promotable) == 1
    assert len(report.agents[0].rejected) == 2
    assert not (dream_root / "DREAMS.md").exists()


def test_deep_write_promotes_and_trims(dream_root: Path):
    pending = (
        "- **agent-browser download:** download @Export often cancels in headless; "
        "prove export via serializeHtk unit tests when file capture fails.\n"
    )
    entry = _write_agent(dream_root, "demo", pending=pending, run_count=32)
    registry = {"agents": [entry]}
    diary = dream_root / ".cursor" / "agent-system" / "DREAMS.md"
    report = run_dream(
        registry,
        dream_root,
        phase="all",
        write=True,
        diary_path=diary,
        llm_rem=False,
    )
    assert len(report.promotions) == 1
    assert report.run_logs_trimmed
    assert report.run_logs_trimmed[0]["removed"] == 2
    spec = (dream_root / entry["spec"]).read_text(encoding="utf-8")
    assert "agent-browser download" in spec
    assert "## Known traps" in spec
    mem = (dream_root / entry["memory"]).read_text(encoding="utf-8")
    assert "agent-browser download" not in mem.split("## Run log")[0]
    assert "last_dream_at=" in mem
    assert mem.count("### 2026-07-") == 30
    assert diary.is_file()
    assert "## REM" in diary.read_text(encoding="utf-8")
    assert "## Deep Sleep" in diary.read_text(encoding="utf-8")


def test_dry_run_all_does_not_write(dream_root: Path):
    pending = (
        "- **stable trap:** always use py -3 for Python on Windows when invoking tester gates.\n"
    )
    entry = _write_agent(dream_root, "demo", pending=pending, run_count=2)
    registry = {"agents": [entry]}
    before_spec = (dream_root / entry["spec"]).read_text(encoding="utf-8")
    before_mem = (dream_root / entry["memory"]).read_text(encoding="utf-8")
    diary = dream_root / "DREAMS.md"
    run_dream(
        registry,
        dream_root,
        phase="all",
        write=False,
        diary_path=diary,
        llm_rem=False,
    )
    assert (dream_root / entry["spec"]).read_text(encoding="utf-8") == before_spec
    assert (dream_root / entry["memory"]).read_text(encoding="utf-8") == before_mem
    assert not diary.exists()


def test_commit_requires_write(dream_root: Path):
    entry = _write_agent(dream_root, "demo", pending="- **x:** " + ("y" * 50), run_count=1)
    with pytest.raises(ValueError, match="--commit requires --write"):
        run_dream(
            {"agents": [entry]},
            dream_root,
            write=False,
            commit=True,
            llm_rem=False,
            diary_path=dream_root / "DREAMS.md",
        )


def test_obsidian_and_bridges_write(dream_root: Path):
    decisions = dream_root / "knowledge" / "obsidian" / "03-Nova-Decisions"
    decisions.mkdir(parents=True)
    (decisions / "Active-Strategy.md").write_text("# Active Strategy\n\nChosen: Gap\n", encoding="utf-8")
    (dream_root / ".claude").mkdir()
    (dream_root / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
    entry = _write_agent(
        dream_root,
        "demo",
        pending=(
            "- **stable trap:** always use py -3 for Python on Windows when invoking tester gates.\n"
        ),
        run_count=2,
    )
    report = run_dream(
        {"agents": [entry]},
        dream_root,
        write=True,
        llm_rem=False,
        obsidian=True,
        bridges=True,
        diary_path=dream_root / ".cursor" / "agent-system" / "DREAMS.md",
    )
    hygiene = decisions / "_Agent-Dream-Hygiene.md"
    assert hygiene.is_file()
    assert "AGENT_DREAM_FOOTER_START" in (decisions / "Active-Strategy.md").read_text(
        encoding="utf-8"
    )
    settings = json.loads((dream_root / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert settings.get("autoDreamEnabled") is True
    assert (dream_root / ".cursor" / "agent-system" / "openclaw-MEMORY.md").is_file()
    assert report.obsidian.get("notes_scanned") == 1
    assert report.bridges.get("actions")


def test_append_promotion_creates_section_without_traps():
    spec = "# A\n\n## Invoke phrases\n\n- hi\n"
    out = append_promotion_to_spec(spec, "A durable fact about routing tables for news.", "x")
    assert "## Dream promotions" in out
    assert "durable fact about routing" in out
    assert out.index("Dream promotions") < out.index("Invoke phrases")


def test_load_agent_memory_parses_backlog(dream_root: Path):
    entry = _write_agent(
        dream_root,
        "demo",
        pending="- **fact:** " + ("x" * 50),
        run_count=1,
    )
    mem = load_agent_memory(
        "demo",
        dream_root / entry["memory"],
        dream_root / entry["spec"],
    )
    assert len(mem.open_backlog) == 1
    assert mem.run_log_entries
    assert mem.learnings
