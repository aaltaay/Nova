"""Dream report model + diary / stdout formatting."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class StagedAgent:
    agent_id: str
    memory_rel: str
    spec_rel: str
    open_backlog_count: int
    pending_count: int
    run_log_count: int
    promotable: list[dict[str, str]] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)
    learnings_sample: list[str] = field(default_factory=list)


@dataclass
class DreamReport:
    phase: str
    dry_run: bool
    captured_at: str
    agents: list[StagedAgent] = field(default_factory=list)
    themes: list[dict[str, Any]] = field(default_factory=list)
    rem_narrative: str | None = None
    rem_mode: str = "heuristic"
    promotions: list[dict[str, str]] = field(default_factory=list)
    run_logs_trimmed: list[dict[str, Any]] = field(default_factory=list)
    diary_appended: bool = False
    files_touched: list[str] = field(default_factory=list)
    obsidian: dict[str, Any] = field(default_factory=dict)
    pinecone: dict[str, Any] = field(default_factory=dict)
    bridges: dict[str, Any] = field(default_factory=dict)
    git: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def format_diary(report: DreamReport) -> str:
    lines = [
        f"### {report.captured_at[:10]} — dream ({report.phase})",
        "",
        f"- **Mode:** {'dry-run' if report.dry_run else 'write'}",
        f"- **Agents scanned:** {len(report.agents)}",
        f"- **REM mode:** {report.rem_mode}",
    ]
    pending = sum(a.pending_count for a in report.agents)
    lines.append(f"- **Pending facts:** {pending}")
    lines.append(f"- **Promotions:** {len(report.promotions)}")
    if report.themes:
        theme_s = ", ".join(f"{t['theme']}×{t['count']}" for t in report.themes[:6])
        lines.append(f"- **REM themes:** {theme_s}")
    if report.rem_narrative:
        lines.append("")
        lines.append("#### Dream Diary")
        lines.append("")
        lines.append(report.rem_narrative.strip())
        lines.append("")
    if report.run_logs_trimmed:
        trim_s = ", ".join(
            f"{t['agent_id']}(-{t['removed']})" for t in report.run_logs_trimmed
        )
        lines.append(f"- **Run logs trimmed:** {trim_s}")
    if report.promotions:
        lines.append("- **Promoted:**")
        for p in report.promotions[:12]:
            short = p["text"][:120] + ("…" if len(p["text"]) > 120 else "")
            lines.append(f"  - `{p['agent_id']}`: {short}")
    if report.obsidian:
        lines.append(
            f"- **Obsidian:** scanned={report.obsidian.get('notes_scanned')} "
            f"findings={report.obsidian.get('findings_count')}"
        )
    if report.pinecone.get("ran"):
        lines.append(
            f"- **Pinecone:** exit={report.pinecone.get('exit_code')} "
            f"dry_run={report.pinecone.get('dry_run')}"
        )
    lines.append("")
    return "\n".join(lines)


def append_diary(diary_path: Path, body: str, *, write: bool) -> bool:
    if not write:
        return False
    diary_path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Agent Dreams\n\n"
        "Nova fleet memory consolidation diary (REM + Deep). Not a promotion source.\n\n"
    )
    if diary_path.is_file():
        existing = diary_path.read_text(encoding="utf-8")
        if not existing.lstrip().startswith("#"):
            existing = header + existing
        new_text = existing.rstrip() + "\n\n" + body
    else:
        new_text = header + body
    diary_path.write_text(new_text, encoding="utf-8", newline="\n")
    return True


def report_text(report: DreamReport) -> str:
    lines = [
        f"Nova agent dream - phase={report.phase} "
        f"mode={'write' if not report.dry_run else 'dry-run'}",
        f"captured_at={report.captured_at}",
        f"rem_mode={report.rem_mode}",
        "",
    ]
    for a in report.agents:
        lines.append(
            f"[{a.agent_id}] backlog={a.open_backlog_count} pending={a.pending_count} "
            f"run_log={a.run_log_count} promotable={len(a.promotable)} "
            f"rejected={len(a.rejected)}"
        )
        for p in a.promotable:
            lines.append(f"  + {p['text'][:100]}")
        for r in a.rejected[:5]:
            lines.append(f"  - ({r['reason']}) {r['text'][:80]}")
    if report.themes:
        lines.append("")
        lines.append(
            "REM themes: " + ", ".join(f"{t['theme']}×{t['count']}" for t in report.themes)
        )
    if report.rem_narrative:
        lines.append("")
        lines.append("REM diary:")
        lines.append(report.rem_narrative[:800])
    if report.promotions:
        lines.append("")
        lines.append(f"Deep promotions ({len(report.promotions)}):")
        for p in report.promotions:
            lines.append(f"  -> {p['agent_id']}: {p['text'][:100]}")
    if report.run_logs_trimmed:
        lines.append("")
        lines.append("Run log trims: " + json.dumps(report.run_logs_trimmed))
    if report.obsidian:
        lines.append("")
        lines.append(
            f"Obsidian: scanned={report.obsidian.get('notes_scanned')} "
            f"findings={report.obsidian.get('findings_count')}"
        )
    if report.pinecone.get("ran"):
        lines.append("")
        lines.append(f"Pinecone: {report.pinecone.get('summary')}")
    if report.bridges.get("actions"):
        lines.append("")
        lines.append("Bridges: " + "; ".join(report.bridges["actions"]))
    if report.git:
        lines.append("")
        lines.append(f"Git: {report.git.get('detail')} sha={report.git.get('sha')}")
    if report.files_touched:
        lines.append("")
        lines.append("Files touched: " + ", ".join(report.files_touched))
    elif report.dry_run:
        lines.append("")
        lines.append("No files written (dry-run). Pass --write to apply.")
    return "\n".join(lines) + "\n"
