#!/usr/bin/env python3
"""Validate Nova custom agents against the versioned agent-system contract.

Filesystem discovery is authoritative: every ``*.md`` under ``.cursor/agents/``
must be a registered agent prompt. Exit 0 on success, 1 on structural failure.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / ".cursor" / "agent-system" / "contract.json"
REGISTRY_PATH = REPO_ROOT / ".cursor" / "agent-system" / "registry.json"
AGENTS_DIR = REPO_ROOT / ".cursor" / "agents"
MEMORY_DIR = REPO_ROOT / ".cursor" / "agent-memory"
AGENTS_MD = REPO_ROOT / "AGENTS.md"
CANVAS_DIR = (
    Path.home()
    / ".cursor"
    / "projects"
    / "c-Users-aalta-github-Nova"
    / "canvases"
)

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
NAME_RE = re.compile(r"^name:\s*([^\n]+)$", re.MULTILINE)
SNAPSHOT_BLOCK_RE = re.compile(
    r"## Current snapshot\s*\n+```ya?ml\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_frontmatter(text: str) -> dict[str, str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    block = m.group(1)
    name_m = NAME_RE.search(block)
    return {"name": name_m.group(1).strip()} if name_m else {}


def has_section(text: str, title: str) -> bool:
    return bool(re.search(rf"^##\s+{re.escape(title)}\b", text, re.MULTILINE))


def discover_agent_files() -> list[Path]:
    if not AGENTS_DIR.is_dir():
        return []
    return sorted(p for p in AGENTS_DIR.glob("*.md") if p.is_file())


def discover_memory_files() -> list[Path]:
    if not MEMORY_DIR.is_dir():
        return []
    return sorted(p for p in MEMORY_DIR.glob("*-memory.md") if p.is_file())


def registry_by_name(registry: dict) -> dict[str, dict]:
    return {a["name"]: a for a in registry.get("agents", [])}


def validate_snapshot(memory_text: str, contract: dict) -> list[str]:
    errors: list[str] = []
    if not has_section(memory_text, "Current snapshot"):
        errors.append("memory missing ## Current snapshot")
        return errors
    m = SNAPSHOT_BLOCK_RE.search(memory_text)
    if not m:
        errors.append("memory Current snapshot missing yaml fenced block")
        return errors
    body = m.group(1)
    for key in contract.get("snapshot_required_keys", []):
        if not re.search(rf"^{re.escape(key)}\s*:", body, re.MULTILINE):
            errors.append(f"snapshot missing key: {key}")
    return errors


def validate_agent(
    path: Path,
    contract: dict,
    registry_map: dict[str, dict],
    *,
    ci: bool,
) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    if not fm.get("name"):
        errors.append(f"{path.name}: missing frontmatter name")
        return errors
    name = fm["name"]
    if path.stem != name:
        errors.append(f"{path.name}: filename stem '{path.stem}' != name '{name}'")
    entry = registry_map.get(name)
    if entry is None:
        errors.append(f"{path.name}: unregistered agent '{name}'")
        return errors

    for section in contract.get("required_prompt_sections", []):
        if not has_section(text, section):
            errors.append(f"{name}: missing section '## {section}'")

    for marker in contract.get("required_prompt_markers", []):
        if marker not in text:
            errors.append(f"{name}: missing marker {marker!r}")

    commit_ok = any(p in text for p in contract.get("commit_safety_phrases", []))
    if not commit_ok:
        errors.append(f"{name}: missing commit-safety phrase")

    mem_rel = entry.get("memory", "")
    mem_path = REPO_ROOT / mem_rel
    if not mem_path.is_file():
        errors.append(f"{name}: memory missing at {mem_rel}")
    else:
        mem_text = mem_path.read_text(encoding="utf-8")
        for section in contract.get("required_memory_sections", []):
            if not has_section(mem_text, section):
                errors.append(f"{name}: memory missing '## {section}'")
        errors.extend(f"{name}: {e}" for e in validate_snapshot(mem_text, contract))

    phrases = entry.get("invoke_phrases") or []
    if not phrases:
        errors.append(f"{name}: registry invoke_phrases empty")
    else:
        # At least one exact phrase must appear in the Invoke phrases section.
        invoke_blob = text
        if not any(p in invoke_blob for p in phrases):
            errors.append(f"{name}: no registered invoke phrase found in spec")

    dash = entry.get("dashboard") or {}
    canvas = dash.get("canvas", "")
    dtype = dash.get("type", "")
    naming = contract.get("dashboard_naming", {})
    if dtype == "dedicated":
        if not canvas.startswith(naming.get("dedicated_prefix", "agent-")):
            errors.append(f"{name}: dedicated canvas must start with agent-")
        if "agent-nova" in canvas:
            errors.append(f"{name}: forbidden agent-nova canvas name")
    elif dtype == "home_section":
        if canvas != naming.get("home_canvas"):
            errors.append(f"{name}: home_section must use nova-home.canvas.tsx")
        if name not in naming.get("home_exception_agents", []):
            errors.append(f"{name}: not listed as home exception agent")
    else:
        errors.append(f"{name}: dashboard.type must be dedicated or home_section")

    if canvas and "Dashboard" in text and canvas.replace(".canvas.tsx", "") not in text:
        # Soft: dashboard path or name should be referenced
        if canvas not in text and canvas.replace(".canvas.tsx", "") not in text:
            errors.append(f"{name}: dashboard canvas not referenced in spec")

    rule = entry.get("continuity_rule")
    waiver = entry.get("continuity_waiver")
    if contract.get("continuity_rule_or_waiver_required"):
        if rule:
            if not (REPO_ROOT / rule).is_file():
                errors.append(f"{name}: continuity_rule missing: {rule}")
        elif not waiver:
            errors.append(f"{name}: needs continuity_rule or continuity_waiver")

    for cmd in entry.get("deterministic_checks") or []:
        # Extract first path-like token that looks like a repo script.
        for token in cmd.split():
            if token.startswith("tools/") and token.endswith(".py"):
                if not (REPO_ROOT / token).is_file():
                    errors.append(f"{name}: declared script missing: {token}")

    if AGENTS_MD.is_file():
        agents_md = AGENTS_MD.read_text(encoding="utf-8")
        if name not in agents_md:
            errors.append(f"{name}: not discoverable in AGENTS.md")

    if not ci and canvas:
        canvas_path = CANVAS_DIR / canvas
        if not canvas_path.is_file():
            errors.append(f"{name}: external canvas missing: {canvas_path}")

    return errors


def validate_orphans(registry_map: dict[str, dict]) -> list[str]:
    errors: list[str] = []
    registered_mem = {
        (REPO_ROOT / a["memory"]).resolve()
        for a in registry_map.values()
        if a.get("memory")
    }
    for mem in discover_memory_files():
        if mem.resolve() not in registered_mem:
            try:
                rel = mem.relative_to(REPO_ROOT).as_posix()
            except ValueError:
                rel = mem.as_posix()
            errors.append(f"orphan memory: {rel}")

    # Non-agent markdown in agents dir: any file whose stem is not a registered name
    for path in discover_agent_files():
        if path.stem not in registry_map:
            errors.append(f"non-agent markdown in agents dir: {path.name}")
        if path.stem.endswith("-memory") or path.name.endswith("-memory.md"):
            errors.append(f"memory file must not live in agents dir: {path.name}")
    return errors


def validate_duplicate_phrases(registry: dict) -> list[str]:
    errors: list[str] = []
    seen: dict[str, str] = {}
    for agent in registry.get("agents", []):
        for phrase in agent.get("invoke_phrases") or []:
            key = phrase.strip().lower()
            if key in seen:
                errors.append(
                    f"duplicate invoke phrase {phrase!r}: "
                    f"{seen[key]} and {agent['name']}"
                )
            else:
                seen[key] = agent["name"]
    return errors


def run_validation(*, ci: bool = False) -> list[str]:
    if not CONTRACT_PATH.is_file() or not REGISTRY_PATH.is_file():
        return ["missing contract.json or registry.json"]
    contract = load_json(CONTRACT_PATH)
    registry = load_json(REGISTRY_PATH)
    registry_map = registry_by_name(registry)
    errors: list[str] = []
    errors.extend(validate_duplicate_phrases(registry))
    discovered = discover_agent_files()
    if not discovered:
        errors.append("no agent prompts discovered under .cursor/agents/")
    for path in discovered:
        errors.extend(validate_agent(path, contract, registry_map, ci=ci))
    # Registry entries must exist on disk
    for name, entry in registry_map.items():
        spec = REPO_ROOT / entry["spec"]
        if not spec.is_file():
            errors.append(f"{name}: registry spec missing: {entry['spec']}")
    errors.extend(validate_orphans(registry_map))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Skip external canvas file existence checks",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON errors")
    args = parser.parse_args(argv)
    errors = run_validation(ci=args.ci)
    if args.json:
        print(json.dumps({"ok": not errors, "errors": errors}, indent=2))
    else:
        if errors:
            print(f"agent_contract: FAIL ({len(errors)} error(s))")
            for e in errors:
                print(f"  - {e}")
        else:
            n = len(discover_agent_files())
            print(f"agent_contract: PASS ({n} agents)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
