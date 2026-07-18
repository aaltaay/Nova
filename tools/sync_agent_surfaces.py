#!/usr/bin/env python3
"""Build dashboard snapshot data from registry + memory + canonical sources.

Read-only by default. Pass ``--write`` to replace generated blocks in canvases.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / ".cursor" / "agent-system" / "registry.json"
FINDINGS_PATH = REPO_ROOT / "security" / "findings-registry.json"
CANVAS_DIR = (
    Path.home()
    / ".cursor"
    / "projects"
    / "c-Users-aalta-github-Nova"
    / "canvases"
)

SNAPSHOT_RE = re.compile(
    r"## Current snapshot\s*\n+```ya?ml\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)
MARKER_START = "/* AGENT_SNAPSHOT_START: {id} */"
MARKER_END = "/* AGENT_SNAPSHOT_END: {id} */"
# JSX comment form used in canvases
JSX_START = "{{/* AGENT_SNAPSHOT_START: {id} */}}"
JSX_END = "{{/* AGENT_SNAPSHOT_END: {id} */}}"


def git_short_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def parse_yaml_simple(block: str) -> dict:
    """Minimal YAML-ish parser for our snapshot keys (no nested objects beyond one level)."""
    data: dict = {}
    metrics: dict = {}
    in_metrics = False
    blockers: list = []
    in_blockers = False
    for raw in block.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.startswith("metrics:"):
            in_metrics = True
            in_blockers = False
            rest = line[len("metrics:") :].strip()
            if rest and rest != "{}":
                pass
            data["metrics"] = metrics
            continue
        if line.startswith("blockers:"):
            in_metrics = False
            in_blockers = True
            rest = line[len("blockers:") :].strip()
            if rest == "[]":
                data["blockers"] = []
            continue
        if in_metrics and line.startswith("  ") and ":" in line:
            k, v = line.strip().split(":", 1)
            metrics[k.strip()] = _coerce(v.strip())
            data["metrics"] = metrics
            continue
        if in_blockers and line.strip().startswith("- "):
            blockers.append(line.strip()[2:].strip().strip("\"'"))
            data["blockers"] = blockers
            continue
        if ":" in line and not line.startswith(" "):
            in_metrics = False
            in_blockers = False
            k, v = line.split(":", 1)
            data[k.strip()] = _coerce(v.strip())
    return data


def _coerce(v: str):
    if v in ("{}", "[]", ""):
        return {} if v == "{}" else ([] if v == "[]" else "")
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    try:
        if "." in v:
            return float(v)
        return int(v)
    except ValueError:
        return v


def load_memory_snapshot(memory_rel: str) -> dict:
    path = REPO_ROOT / memory_rel
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    m = SNAPSHOT_RE.search(text)
    if not m:
        return {}
    return parse_yaml_simple(m.group(1))


def security_counts() -> dict:
    if not FINDINGS_PATH.is_file():
        return {}
    data = json.loads(FINDINGS_PATH.read_text(encoding="utf-8"))
    findings = data.get("findings") or []
    open_f = [f for f in findings if f.get("status") == "open"]
    accepted = [f for f in findings if f.get("status") == "accepted"]
    by_sev: dict[str, int] = {}
    highest = 0.0
    for f in open_f:
        sev = str(f.get("severity") or "unknown").lower()
        by_sev[sev] = by_sev.get(sev, 0) + 1
        score = f.get("cvss_score")
        if isinstance(score, (int, float)) and score > highest:
            highest = float(score)
    return {
        "open_findings": len(open_f),
        "accepted_risks": len(accepted),
        "highest_open_cvss": highest,
        "critical_open": by_sev.get("critical", 0),
        "high_open": by_sev.get("high", 0),
        "medium_open": by_sev.get("medium", 0),
        "low_open": by_sev.get("low", 0),
    }


def build_agent_snapshot(entry: dict, captured_at: str, revision: str) -> dict:
    snap = load_memory_snapshot(entry.get("memory", ""))
    metrics = dict(snap.get("metrics") or {})
    if entry["name"] == "security-sentinel":
        metrics.update(security_counts())
    freshness = snap.get("dashboard_freshness") or "unknown"
    result = snap.get("result") or "unknown"
    return {
        "agent_id": entry["name"],
        "domain": entry.get("domain", ""),
        "captured_at": snap.get("captured_at") or captured_at,
        "source_revision": snap.get("source_revision") or revision,
        "sync_revision": revision,
        "sync_captured_at": captured_at,
        "result": result,
        "metrics": metrics,
        "blockers": snap.get("blockers") or [],
        "dashboard_freshness": freshness,
        "stale": freshness in ("stale", "unknown"),
        "invoke_phrases": entry.get("invoke_phrases") or [],
        "spec": entry.get("spec"),
        "memory": entry.get("memory"),
        "dashboard": entry.get("dashboard"),
        "canonical_inputs": entry.get("canonical_inputs") or [],
    }


def render_tsx_const(agent_id: str, data: dict) -> str:
    """Render a TS const object for embedding inside a generated snapshot block."""
    payload = json.dumps(data, indent=2)
    # Keep as JSON-compatible so it is valid TS object literal for primitives
    return (
        f"  // Generated by tools/sync_agent_surfaces.py — do not hand-edit\n"
        f"  const AGENT_SNAPSHOT_{agent_id.upper().replace('-', '_')} = {payload} as const;\n"
    )


def _snapshot_fingerprint(data: dict) -> str:
    """Stable identity for idempotent writes (ignore wall-clock sync stamp)."""
    slim = {
        k: v
        for k, v in data.items()
        if k not in ("sync_captured_at",)
    }
    return json.dumps(slim, sort_keys=True, default=str)


def _extract_existing_fingerprint(text: str, agent_id: str) -> str | None:
    start = f"{{/* AGENT_SNAPSHOT_START: {agent_id} */}}"
    end = f"{{/* AGENT_SNAPSHOT_END: {agent_id} */}}"
    if start not in text or end not in text:
        return None
    chunk = text[text.index(start) : text.index(end) + len(end)]
    # Pull JSON object after "= "
    m = re.search(r"=\s*(\{.*?\})\s*as const", chunk, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    return _snapshot_fingerprint(data)


def replace_or_insert_block(
    text: str,
    agent_id: str,
    inner: str,
    *,
    fingerprint: str | None = None,
) -> tuple[str, bool]:
    start = f"{{/* AGENT_SNAPSHOT_START: {agent_id} */}}"
    end = f"{{/* AGENT_SNAPSHOT_END: {agent_id} */}}"
    block = f"{start}\n{inner}{end}"
    if start in text and end in text:
        if fingerprint is not None:
            existing = _extract_existing_fingerprint(text, agent_id)
            if existing == fingerprint:
                return text, False
        pattern = re.compile(
            re.escape(start) + r".*?" + re.escape(end),
            re.DOTALL,
        )

        def _repl(_m: re.Match[str]) -> str:
            return block

        new_text, n = pattern.subn(_repl, text, count=1)
        return new_text, n == 1
    # Insert before default export if possible
    m = re.search(r"^export default function", text, re.MULTILINE)
    if m:
        insert_at = m.start()
        new_text = text[:insert_at] + block + "\n\n" + text[insert_at:]
        return new_text, True
    return text + "\n" + block + "\n", True


AGENT_TITLES = {
    "daddy": "Daddy",
    "nova-agent": "Nova Agent",
    "tester": "Tester",
    "maintainer": "Maintainer",
    "security-sentinel": "Security Sentinel",
    "warrior": "Warrior Navigator",
    "hod-momo": "HOD Momo Parity",
    "widgets-agent": "Widgets Agent",
    "nova-router": "Nova Router",
    "execution": "Execution Auditor",
    "ibkr-ops": "IBKR Ops",
    "backtester": "Backtester",
    "market-feed": "Market Feed",
    "news-catalyst": "News Catalyst",
}


def home_agents_block(snapshots: list[dict]) -> str:
    rows = []
    for s in snapshots:
        mid = s["metrics"]
        summary = s["result"]
        if s["agent_id"] == "security-sentinel":
            summary = f"{mid.get('open_findings', '?')} open"
        elif s["agent_id"] == "maintainer":
            summary = f"{mid.get('findings_total', mid.get('findings', '?'))} findings"
        elif s["agent_id"] == "tester":
            summary = f"pytest {mid.get('pytest_passed', '?')}"
        dash = s.get("dashboard") or {}
        phrases = s.get("invoke_phrases") or []
        rows.append(
            {
                "id": s["agent_id"],
                "title": AGENT_TITLES.get(s["agent_id"], s["agent_id"]),
                "domain": s["domain"],
                "summary": str(summary),
                "invoke": phrases[0] if phrases else "",
                "canvas": dash.get("canvas") or "",
                "dashboard_type": dash.get("type") or "",
                "stale": s["stale"],
                "revision": s["source_revision"],
                "captured_at": s["captured_at"],
            }
        )
    payload = json.dumps(
        {
            "kind": "nova-home-agents",
            "agents": rows,
            "sync_captured_at": snapshots[0]["sync_captured_at"] if snapshots else "",
            "sync_revision": snapshots[0]["sync_revision"] if snapshots else "",
        },
        indent=2,
    )
    return (
        "  // Generated by tools/sync_agent_surfaces.py — do not hand-edit\n"
        f"  const NOVA_HOME_AGENT_SNAPSHOT = {payload} as const;\n"
    )


def fleet_cracks_block() -> str:
    """Nova Home 'Fleet cracks' rollup — lazy import avoids a load-time cycle
    (agent_fleet imports AGENT_TITLES/CANVAS_DIR/load_memory_snapshot from
    this module)."""
    import agent_fleet as _fleet

    report = _fleet.build_report()
    payload = json.dumps(
        {
            "kind": "nova-home-fleet-cracks",
            "crack_count": report["crack_count"],
            "cracks": report["cracks"][:8],
            "open_backlog_total": sum(report["open_backlog_by_agent"].values()),
            "captured_at": report["captured_at"],
            "revision": report["revision"],
        },
        indent=2,
    )
    return (
        "  // Generated by tools/sync_agent_surfaces.py — do not hand-edit\n"
        f"  const NOVA_HOME_FLEET_CRACKS = {payload} as const;\n"
    )


def sync(*, write: bool) -> dict:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    revision = git_short_sha()
    snapshots = [
        build_agent_snapshot(a, captured_at, revision) for a in registry.get("agents", [])
    ]
    plan: list[dict] = []
    for snap in snapshots:
        dash = snap.get("dashboard") or {}
        canvas_name = dash.get("canvas")
        if not canvas_name:
            continue
        canvas_path = CANVAS_DIR / canvas_name
        agent_id = snap["agent_id"]
        if dash.get("type") == "home_section":
            continue  # handled in home pass
        inner = render_tsx_const(agent_id, snap)
        plan.append(
            {
                "path": str(canvas_path),
                "agent_id": agent_id,
                "exists": canvas_path.is_file(),
                "inner": inner,
            }
        )

    # Nova Home registry cards block
    home_path = CANVAS_DIR / "nova-home.canvas.tsx"
    plan.append(
        {
            "path": str(home_path),
            "agent_id": "nova-home-agents",
            "exists": home_path.is_file(),
            "inner": home_agents_block(snapshots),
        }
    )
    plan.append(
        {
            "path": str(home_path),
            "agent_id": "nova-home-fleet-cracks",
            "exists": home_path.is_file(),
            "inner": fleet_cracks_block(),
        }
    )

    writes = 0
    for item in plan:
        path = Path(item["path"])
        if not path.is_file():
            continue
        original = path.read_text(encoding="utf-8")
        # Build fingerprint from the const payload inside inner
        fp = None
        m = re.search(r"=\s*(\{.*?\})\s*as const", item["inner"], re.DOTALL)
        if m:
            try:
                fp = _snapshot_fingerprint(json.loads(m.group(1)))
            except json.JSONDecodeError:
                fp = None
        new_text, changed = replace_or_insert_block(
            original, item["agent_id"], item["inner"], fingerprint=fp
        )
        item["changed"] = bool(changed and new_text != original)
        if write and item["changed"]:
            path.write_text(new_text, encoding="utf-8", newline="\n")
            writes += 1
        elif write and not item["changed"] and (
            f"AGENT_SNAPSHOT_START: {item['agent_id']}" not in original
        ):
            path.write_text(new_text, encoding="utf-8", newline="\n")
            item["changed"] = True
            writes += 1

    return {
        "captured_at": captured_at,
        "revision": revision,
        "agents": len(snapshots),
        "writes": writes,
        "write_mode": write,
        "snapshots": snapshots,
        "plan": [
            {
                "path": p["path"],
                "agent_id": p["agent_id"],
                "exists": p["exists"],
                "changed": p.get("changed", False),
            }
            for p in plan
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write canvas files")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = sync(write=args.write)
    if args.json:
        # Drop bulky inners from plan
        print(json.dumps({k: v for k, v in result.items() if k != "snapshots"}, indent=2))
        print(json.dumps({"snapshots": result["snapshots"]}, indent=2))
    else:
        mode = "WRITE" if args.write else "DRY-RUN"
        print(
            f"sync_agent_surfaces: {mode} · agents={result['agents']} · "
            f"writes={result['writes']} · rev={result['revision']}"
        )
        for p in result["plan"]:
            flag = "changed" if p.get("changed") else ("missing" if not p["exists"] else "ok")
            print(f"  [{flag}] {p['agent_id']} -> {p['path']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
