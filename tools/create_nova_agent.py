#!/usr/bin/env python3
"""Scaffold a new Nova custom agent from versioned templates.

Dry-run by default. Pass ``--write`` to create files. Refuses collisions,
overlapping invoke phrases, invalid canvas names, and overwrites.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SYSTEM_DIR = REPO_ROOT / ".cursor" / "agent-system"
AGENTS_DIR = REPO_ROOT / ".cursor" / "agents"
MEMORY_DIR = REPO_ROOT / ".cursor" / "agent-memory"
REGISTRY_PATH = SYSTEM_DIR / "registry.json"
AGENT_TEMPLATE = SYSTEM_DIR / "agent-template.md"
MEMORY_TEMPLATE = SYSTEM_DIR / "memory-template.md"

logger = logging.getLogger(__name__)

ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,40}$")


def load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def fill(template: str, mapping: dict[str, str]) -> str:
    out = template
    for k, v in mapping.items():
        out = out.replace("{{" + k + "}}", v)
    leftover = re.findall(r"\{\{[A-Z0-9_]+\}\}", out)
    if leftover:
        raise ValueError(f"unfilled template placeholders: {leftover}")
    return out


def validate_args(args: argparse.Namespace, registry: dict) -> list[str]:
    errors: list[str] = []
    if not ID_RE.match(args.id):
        errors.append("id must match ^[a-z][a-z0-9-]{1,40}$")
    names = {a["name"] for a in registry.get("agents", [])}
    if args.id in names:
        errors.append(f"agent id already registered: {args.id}")
    if (AGENTS_DIR / f"{args.id}.md").exists():
        errors.append(f"spec already exists: .cursor/agents/{args.id}.md")
    if (MEMORY_DIR / f"{args.id}-memory.md").exists():
        errors.append(f"memory already exists: .cursor/agent-memory/{args.id}-memory.md")

    phrases = [
        args.invoke or f"Use the {args.id} subagent to",
        f"Improve the {args.id} agent — work the next backlog item",
    ]
    existing = {
        p.strip().lower()
        for a in registry.get("agents", [])
        for p in (a.get("invoke_phrases") or [])
    }
    for p in phrases:
        if p.strip().lower() in existing:
            errors.append(f"overlapping invoke phrase: {p!r}")

    if args.home_section:
        canvas = "nova-home.canvas.tsx"
        dtype = "home_section"
    else:
        canvas = args.canvas or f"agent-{args.id}.canvas.tsx"
        dtype = "dedicated"
        if not canvas.startswith("agent-") or "agent-nova" in canvas:
            errors.append(f"invalid dedicated canvas name: {canvas}")
        if not canvas.endswith(".canvas.tsx"):
            errors.append("canvas must end with .canvas.tsx")

    args._phrases = phrases  # noqa: SLF001
    args._canvas = canvas  # noqa: SLF001
    args._dtype = dtype  # noqa: SLF001
    return errors


def build_entry(args: argparse.Namespace, now: str, sha: str) -> dict:
    waiver = args.continuity_waiver or (
        None
        if args.continuity_rule
        else f"Waiver pending domain continuity rule for {args.id}."
    )
    return {
        "id": args.id,
        "name": args.id,
        "spec": f".cursor/agents/{args.id}.md",
        "memory": f".cursor/agent-memory/{args.id}-memory.md",
        "invoke_phrases": args._phrases,
        "dashboard": {"type": args._dtype, "canvas": args._canvas},
        "continuity_rule": args.continuity_rule,
        "continuity_waiver": waiver,
        "canonical_inputs": [f".cursor/agent-memory/{args.id}-memory.md"],
        "writable_paths": [
            f".cursor/agents/{args.id}.md",
            f".cursor/agent-memory/{args.id}-memory.md",
        ],
        "prohibited_actions": [
            "arm_executor",
            "place_orders",
            "commit_without_ask",
        ],
        "deterministic_checks": [],
        "sibling_handoffs": {
            "tester": "test / build gates",
            "maintainer": "code hygiene",
            "security": "security posture",
            "docs": "docs / canvases",
        },
        "domain": args.domain,
    }


def remaining_steps(args: argparse.Namespace) -> list[str]:
    return [
        "Fill domain-specific Verified commands and deterministic checks in the spec + registry.",
        "Confirm Hard constraints / prohibited_actions match the domain.",
        "Add a continuity rule under .cursor/rules/ or keep the registry waiver.",
        "If dedicated dashboard: create the canvas under the Cursor canvases folder with snapshot markers.",
        "Run: py -3 tools/sync_agent_surfaces.py --write",
        "Run: py -3 tools/agent_contract.py",
        "Smoke-invoke with the registered phrase and confirm the Lifecycle footer.",
        "Add the agent to AGENTS.md specialized-subagents table.",
    ]


def scaffold(args: argparse.Namespace, *, write: bool) -> dict:
    registry = load_registry()
    errors = validate_args(args, registry)
    if errors:
        return {"ok": False, "errors": errors}

    now = datetime.now(timezone.utc)
    captured = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    date = now.strftime("%Y-%m-%d")
    try:
        import subprocess

        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        sha = "unknown"

    if args.home_section:
        dash_ref = (
            "`nova-home.canvas.tsx` (Home section — do **not** create "
            f"`agent-{args.id}.canvas.tsx`)"
        )
    else:
        dash_ref = f"`{args._canvas}` (dedicated agent dashboard)"

    mapping = {
        "AGENT_ID": args.id,
        "AGENT_TITLE": args.title,
        "DESCRIPTION": args.description or f"{args.title}. Domain: {args.domain}.",
        "ONE_LINE_MISSION": args.mission or f"Own the {args.domain} domain.",
        "DASHBOARD_REF": dash_ref,
        "MISSION_1": args.mission or f"Execute deterministic checks for {args.domain}.",
        "PERMISSION_SUMMARY": args.permissions
        or "Report-only unless the parent explicitly expands write scope.",
        "GATE_NAME": "Domain check (fill me)",
        "GATE_COMMAND": "echo fill-domain-check",
        "REPORT_TITLE": f"{args.title} report",
        "PRIMARY_INVOKE": args._phrases[0],
        "CAPTURED_AT": captured,
        "SOURCE_REVISION": sha,
        "CAPTURED_AT_DATE": date,
    }

    agent_body = fill(AGENT_TEMPLATE.read_text(encoding="utf-8"), mapping)
    memory_body = fill(MEMORY_TEMPLATE.read_text(encoding="utf-8"), mapping)
    entry = build_entry(args, captured, sha)

    result = {
        "ok": True,
        "write": write,
        "spec": f".cursor/agents/{args.id}.md",
        "memory": f".cursor/agent-memory/{args.id}-memory.md",
        "entry": entry,
        "remaining_steps": remaining_steps(args),
    }

    if not write:
        result["dry_run"] = True
        return result

    # Atomic-ish: write new files first; only then update registry.
    written: list[Path] = []
    try:
        AGENTS_DIR.mkdir(parents=True, exist_ok=True)
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        spec_path = AGENTS_DIR / f"{args.id}.md"
        mem_path = MEMORY_DIR / f"{args.id}-memory.md"
        if spec_path.exists() or mem_path.exists():
            raise FileExistsError("refusing overwrite")
        spec_path.write_text(agent_body, encoding="utf-8", newline="\n")
        written.append(spec_path)
        mem_path.write_text(memory_body, encoding="utf-8", newline="\n")
        written.append(mem_path)
        registry.setdefault("agents", []).append(entry)
        registry["updated_at"] = date
        REGISTRY_PATH.write_text(
            json.dumps(registry, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except Exception as exc:
        for p in written:
            try:
                p.unlink()
            except OSError as unlink_exc:
                logger.warning("rollback: could not remove %s: %s", p, unlink_exc)
        return {"ok": False, "errors": [f"rollback after failure: {exc}"]}

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--mission", default="")
    parser.add_argument("--permissions", default="")
    parser.add_argument("--invoke", default="")
    parser.add_argument("--canvas", default="")
    parser.add_argument("--home-section", action="store_true")
    parser.add_argument("--continuity-rule", default=None)
    parser.add_argument("--continuity-waiver", default=None)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = scaffold(args, write=args.write)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if not result.get("ok"):
            print("create_nova_agent: FAIL")
            for e in result.get("errors", []):
                print(f"  - {e}")
            return 1
        mode = "WRITE" if args.write else "DRY-RUN"
        print(f"create_nova_agent: {mode} · id={args.id}")
        print(f"  spec: {result['spec']}")
        print(f"  memory: {result['memory']}")
        print("  Remaining human/domain steps:")
        for step in result["remaining_steps"]:
            print(f"    - {step}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
