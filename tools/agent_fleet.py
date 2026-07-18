#!/usr/bin/env python3
"""Cross-agent crack index for Nova's agent OS.

Read-only. Unions signals that today live in 7 separate memories, the
domain/skill ownership matrix, and the canvases directory so "what's in the
cracks" is one command instead of opening every agent's memory file.

Sources (never mutated by this tool):
- .cursor/agent-system/registry.json  (agent wiring)
- .cursor/agent-memory/*-memory.md    (per-agent snapshot + backlog)
- knowledge/obsidian/00-System/Agent-Fleet-Map.md (domain/skill ownership)
- ~/.cursor/projects/.../canvases/    (dashboard files on disk)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_TOOLS_DIR = str(REPO_ROOT / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from sync_agent_surfaces import (  # noqa: E402
    AGENT_TITLES,
    CANVAS_DIR,
    git_short_sha,
    load_memory_snapshot,
)

FLEET_MAP_PATH = REPO_ROOT / "knowledge" / "obsidian" / "00-System" / "Agent-Fleet-Map.md"
REGISTRY_PATH = REPO_ROOT / ".cursor" / "agent-system" / "registry.json"

STALE_SNAPSHOT_DAYS = 7
CANVAS_ALLOWLIST_PREFIXES = ("context-usage-",)
CANVAS_ALLOWLIST_NAMES = {
    "nova-home.canvas.tsx",
    "nova-design-audit.canvas.tsx",
}

BACKLOG_ITEM_RE = re.compile(r"^-\s*\[ \]\s*(.+)$")
TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$")


@dataclass
class Crack:
    kind: str  # stale_snapshot | open_blocker | unowned_domain | orphan_skill | unmanaged_canvas | missing_title
    severity: str  # structural | blocker | stale | info
    subject: str  # agent id, domain name, skill name, or canvas filename
    detail: str
    age_days: float | None = None


def load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _parse_captured_at(value: str) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _days_since(dt: datetime | None, now: datetime) -> float | None:
    if dt is None:
        return None
    return round((now - dt).total_seconds() / 86400.0, 1)


def parse_backlog(memory_rel: str) -> list[str]:
    """Open ('- [ ]') items under '## Backlog', stopping at '### Completed'."""
    path = REPO_ROOT / memory_rel
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^## Backlog\s*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if not m:
        return []
    section = m.group(1)
    completed_idx = section.find("### Completed")
    if completed_idx != -1:
        section = section[:completed_idx]
    items: list[str] = []
    for line in section.splitlines():
        bm = BACKLOG_ITEM_RE.match(line.strip())
        if bm:
            items.append(bm.group(1).strip())
    return items


def parse_fleet_map_table(section_title: str) -> list[dict[str, str]]:
    """Parse a markdown table under '## {section_title}' into row dicts."""
    if not FLEET_MAP_PATH.is_file():
        return []
    text = FLEET_MAP_PATH.read_text(encoding="utf-8")
    m = re.search(
        rf"^## {re.escape(section_title)}\s*\n(.*?)(?=^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not m:
        return []
    lines = [ln for ln in m.group(1).splitlines() if TABLE_ROW_RE.match(ln)]
    if len(lines) < 2:
        return []
    header = [c.strip() for c in lines[0].strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for line in lines[2:]:  # skip header + separator
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(header):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def find_stale_snapshots(registry: dict, now: datetime) -> list[Crack]:
    cracks: list[Crack] = []
    for agent in registry.get("agents", []):
        snap = load_memory_snapshot(agent.get("memory", ""))
        if not snap:
            continue
        captured = _parse_captured_at(str(snap.get("captured_at", "")))
        age = _days_since(captured, now)
        freshness = snap.get("dashboard_freshness") or "unknown"
        if age is not None and age > STALE_SNAPSHOT_DAYS:
            cracks.append(
                Crack(
                    kind="stale_snapshot",
                    severity="stale",
                    subject=agent["id"],
                    detail=f"snapshot captured_at is {age:.1f}d old (>{STALE_SNAPSHOT_DAYS}d threshold)",
                    age_days=age,
                )
            )
        elif captured is None:
            cracks.append(
                Crack(
                    kind="stale_snapshot",
                    severity="stale",
                    subject=agent["id"],
                    detail="captured_at unparseable — freshness unknown",
                    age_days=None,
                )
            )
        elif freshness not in ("clean",):
            cracks.append(
                Crack(
                    kind="stale_snapshot",
                    severity="stale",
                    subject=agent["id"],
                    detail=f"dashboard_freshness self-reported as {freshness!r}",
                    age_days=age,
                )
            )
    return cracks


def find_open_blockers(registry: dict) -> list[Crack]:
    cracks: list[Crack] = []
    for agent in registry.get("agents", []):
        snap = load_memory_snapshot(agent.get("memory", ""))
        for blocker in snap.get("blockers") or []:
            cracks.append(
                Crack(
                    kind="open_blocker",
                    severity="blocker",
                    subject=agent["id"],
                    detail=str(blocker),
                )
            )
    return cracks


def find_ownership_gaps() -> list[Crack]:
    cracks: list[Crack] = []
    for row in parse_fleet_map_table("Domain ownership"):
        status = row.get("Status", "")
        name = row.get("Domain", "unknown")
        if status in ("Unowned", "Continuity-only"):
            cracks.append(
                Crack(
                    kind="unowned_domain",
                    severity="structural" if status == "Unowned" else "info",
                    subject=name,
                    detail=f"{status}: {row.get('Notes', '')}".strip(": "),
                )
            )
    for row in parse_fleet_map_table("Skill ownership"):
        status = row.get("Status", "")
        name = row.get("Skill", "unknown")
        if status == "Orphan":
            cracks.append(
                Crack(
                    kind="orphan_skill",
                    severity="info",
                    subject=name,
                    detail=row.get("Notes", ""),
                )
            )
    return cracks


def find_unmanaged_canvases(registry: dict) -> list[Crack]:
    if not CANVAS_DIR.is_dir():
        return []
    registered = {
        (a.get("dashboard") or {}).get("canvas")
        for a in registry.get("agents", [])
        if (a.get("dashboard") or {}).get("canvas")
    }
    cracks: list[Crack] = []
    for path in sorted(CANVAS_DIR.glob("*.canvas.tsx")):
        name = path.name
        if name in registered or name in CANVAS_ALLOWLIST_NAMES:
            continue
        if any(name.startswith(p) for p in CANVAS_ALLOWLIST_PREFIXES):
            continue
        cracks.append(
            Crack(
                kind="unmanaged_canvas",
                severity="structural",
                subject=name,
                detail="canvas on disk is not registered to any agent's dashboard",
            )
        )
    return cracks


def find_missing_titles(registry: dict) -> list[Crack]:
    cracks: list[Crack] = []
    for agent in registry.get("agents", []):
        if agent["id"] not in AGENT_TITLES:
            cracks.append(
                Crack(
                    kind="missing_title",
                    severity="structural",
                    subject=agent["id"],
                    detail="missing from sync_agent_surfaces.AGENT_TITLES — Home rollup falls back to raw id",
                )
            )
    return cracks


SEVERITY_ORDER = {"structural": 0, "blocker": 1, "stale": 2, "info": 3}


def collect_cracks(registry: dict, now: datetime) -> list[Crack]:
    cracks: list[Crack] = []
    cracks.extend(find_missing_titles(registry))
    cracks.extend(find_unmanaged_canvases(registry))
    cracks.extend(find_open_blockers(registry))
    cracks.extend(find_stale_snapshots(registry, now))
    cracks.extend(find_ownership_gaps())
    cracks.sort(key=lambda c: (SEVERITY_ORDER.get(c.severity, 9), -(c.age_days or 0)))
    return cracks


def backlog_summary(registry: dict) -> dict[str, int]:
    return {
        agent["id"]: len(parse_backlog(agent.get("memory", "")))
        for agent in registry.get("agents", [])
    }


def build_report(*, now: datetime | None = None) -> dict:
    registry = load_registry()
    now = now or datetime.now(timezone.utc)
    cracks = collect_cracks(registry, now)
    return {
        "captured_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "revision": git_short_sha(),
        "agents": len(registry.get("agents", [])),
        "crack_count": len(cracks),
        "cracks": [asdict(c) for c in cracks],
        "open_backlog_by_agent": backlog_summary(registry),
    }


def build_session_brief(report: dict, *, top_n: int = 3) -> dict:
    top = report["cracks"][:top_n]
    return {
        "captured_at": report["captured_at"],
        "revision": report["revision"],
        "crack_count": report["crack_count"],
        "top_cracks": [
            f"[{c['severity']}] {c['subject']}: {c['detail']}" for c in top
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit full report as JSON")
    parser.add_argument(
        "--session-brief",
        action="store_true",
        help="Emit compact top-N cracks brief as JSON (for sessionStart hook)",
    )
    parser.add_argument("--top", type=int, default=3, help="Top-N cracks for --session-brief")
    args = parser.parse_args(argv)

    report = build_report()

    if args.session_brief:
        print(json.dumps(build_session_brief(report, top_n=args.top), indent=2))
        return 0

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(
        f"agent_fleet: {report['crack_count']} crack(s) · "
        f"{report['agents']} agents · rev={report['revision']}"
    )
    for c in report["cracks"]:
        age = f" ({c['age_days']}d)" if c.get("age_days") is not None else ""
        print(f"  [{c['severity']}] {c['kind']} · {c['subject']}{age}: {c['detail']}")
    if not report["cracks"]:
        print("  (none — fleet clean)")
    backlog = report["open_backlog_by_agent"]
    total_backlog = sum(backlog.values())
    print(f"  open backlog items: {total_backlog} total across {len(backlog)} agents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
