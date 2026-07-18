"""Conservative hygiene for knowledge/obsidian/03-Nova-Decisions/."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DECISIONS_REL = "knowledge/obsidian/03-Nova-Decisions"
HYGIENE_NAME = "_Agent-Dream-Hygiene.md"
FOOTER_START = "<!-- AGENT_DREAM_FOOTER_START -->"
FOOTER_END = "<!-- AGENT_DREAM_FOOTER_END -->"
STRATEGY_STAMP_TARGETS = (
    "Active-Strategy.md",
    "Automation-Strategy-Backbone.md",
    "Automation-Roadmap.md",
)


@dataclass
class ObsidianFinding:
    path: str
    kind: str
    detail: str


@dataclass
class ObsidianReport:
    findings: list[ObsidianFinding] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)
    notes_scanned: int = 0


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")


def _rel(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def scan_decisions(repo_root: Path) -> ObsidianReport:
    root = repo_root / DECISIONS_REL
    report = ObsidianReport()
    if not root.is_dir():
        report.findings.append(
            ObsidianFinding(DECISIONS_REL, "missing", "decisions folder not found")
        )
        return report

    for path in sorted(root.glob("*.md")):
        if path.name.startswith("_"):
            continue
        report.notes_scanned += 1
        text = path.read_text(encoding="utf-8")
        rel = _rel(repo_root, path)
        if re.search(r"(?i)superseded|deprecated|do not use", text):
            report.findings.append(
                ObsidianFinding(rel, "supersede_marker", "contains superseded/deprecated language")
            )
        if re.search(r"(?i)^##\s*Crash/?blocker", text, re.MULTILINE):
            # Empty crash section is healthy; non-empty is a live signal
            m = re.search(
                r"(?i)^##\s*Crash/?blocker\s*\n+(.*?)(?=^## |\Z)",
                text,
                re.MULTILINE | re.DOTALL,
            )
            body = (m.group(1) if m else "").strip()
            if body and body.lower() not in {"(none)", "none", "-", "n/a"}:
                if len(body) > 40:
                    report.findings.append(
                        ObsidianFinding(rel, "open_blocker", body.splitlines()[0][:160])
                    )
        if "TODO" in text or "- [ ]" in text:
            open_boxes = len(re.findall(r"^- \[ \] ", text, re.MULTILINE))
            if open_boxes >= 3:
                report.findings.append(
                    ObsidianFinding(rel, "open_checkboxes", f"{open_boxes} open checkboxes")
                )
    return report


def _hygiene_markdown(report: ObsidianReport, when: str) -> str:
    lines = [
        "# Agent Dream Hygiene (Nova Decisions)",
        "",
        f"Auto-maintained by `tools/agent_dream.py` on **{when}**. "
        "Human decisions remain highest trust — this note is an inventory, not a rewrite of strategy truth.",
        "",
        f"- **Notes scanned:** {report.notes_scanned}",
        f"- **Findings:** {len(report.findings)}",
        "",
        "## Findings",
        "",
    ]
    if not report.findings:
        lines.append("(none — vault looks tidy)")
    else:
        for f in report.findings:
            lines.append(f"- `{f.path}` — **{f.kind}**: {f.detail}")
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- Dream may stamp strategy notes with a footer pointing here.",
            "- Dream does **not** change Chosen strategy / Mechanical rules without a human.",
            "- Clear Crash/blocker sections in status ledgers when the incident is truly closed.",
            "",
        ]
    )
    return "\n".join(lines)


def _stamp_footer(text: str, when: str, hygiene_wikilink: str) -> str:
    footer = (
        f"\n{FOOTER_START}\n"
        f"**Last agent dream pass:** {when} · hygiene: [[{hygiene_wikilink}]] · "
        f"run `py -3 tools/agent_dream.py`\n"
        f"{FOOTER_END}\n"
    )
    if FOOTER_START in text and FOOTER_END in text:
        return re.sub(
            re.escape(FOOTER_START) + r".*?" + re.escape(FOOTER_END),
            footer.strip(),
            text,
            count=1,
            flags=re.DOTALL,
        )
    return text.rstrip() + "\n" + footer


def apply_obsidian_hygiene(
    repo_root: Path,
    *,
    write: bool,
    when: str | None = None,
) -> ObsidianReport:
    when = when or _now()
    report = scan_decisions(repo_root)
    decisions = repo_root / DECISIONS_REL
    hygiene_path = decisions / HYGIENE_NAME
    body = _hygiene_markdown(report, when)

    if write:
        decisions.mkdir(parents=True, exist_ok=True)
        hygiene_path.write_text(body, encoding="utf-8", newline="\n")
        report.files_touched.append(_rel(repo_root, hygiene_path))
        wikilink = HYGIENE_NAME.replace(".md", "")
        for name in STRATEGY_STAMP_TARGETS:
            target = decisions / name
            if not target.is_file():
                continue
            old = target.read_text(encoding="utf-8")
            new = _stamp_footer(old, when, wikilink)
            if new != old:
                target.write_text(new, encoding="utf-8", newline="\n")
                report.files_touched.append(_rel(repo_root, target))
    return report
