"""Audit Nova engineering-methodology graft (skills + always-on rules).

Validates that Superpowers/Addy grafts exist, stay Nova-shaped (domain
constitution wins, zero-hop preserved, no auto_live bypass), and remain
indexed. Intended as a cold-session regression check after skill edits.

Usage:
  py -3 tools/engineering_skills_audit.py
  py -3 tools/engineering_skills_audit.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_SKILLS: tuple[str, ...] = (
    "verification-before-completion",
    "writing-plans",
    "interview-me",
    "doubt-driven-development",
    "code-review-and-quality",
    "github-delivery",
)

REQUIRED_ALWAYS_ON_MDC: tuple[str, ...] = (
    "verification-before-completion.mdc",
    "engineering-methodology.mdc",
    "github-delivery.mdc",
)

# Phrases that must NOT appear as instructions to weaken Nova law.
FORBIDDEN_SKILL_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "enable_auto_live",
        re.compile(r"(?i)\benable\s+auto_live\b"),
        "Skill must not instruct enabling auto_live.",
    ),
    (
        "replace_agents_md",
        re.compile(r"(?i)replace\s+AGENTS\.md"),
        "Skill must not replace the Nova constitution.",
    ),
    (
        "default_subagent_per_task",
        re.compile(r"(?i)REQUIRED SUB-SKILL:\s*Use\s+superpowers:subagent-driven-development"),
        "Must not require Superpowers subagent-per-task (conflicts with zero-hop).",
    ),
    (
        "place_orders_outside_ibkr",
        re.compile(r"(?i)place\s+orders\s+via\s+alpaca"),
        "Skill must not route orders through Alpaca.",
    ),
)

REQUIRED_SKILL_MARKERS: tuple[str, ...] = (
    "Nova",
    "auto_live",
)

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
NAME_RE = re.compile(r"(?m)^name:\s*([a-z0-9-]+)\s*$")
DESC_RE = re.compile(r"(?ms)^description:\s*(?:>-\s*)?(.*?)(?=^[a-zA-Z_-]+:|\Z)")


@dataclass
class Finding:
    severity: str  # error | warn | info
    code: str
    path: str
    message: str


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def _skill_dir(name: str) -> Path:
    return REPO_ROOT / ".cursor" / "skills" / name


def _parse_frontmatter(text: str) -> dict[str, str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    block = m.group(1)
    name_m = NAME_RE.search(block)
    # description may be folded YAML
    desc = ""
    if "description:" in block:
        after = block.split("description:", 1)[1]
        lines = after.splitlines()
        chunks: list[str] = []
        for i, line in enumerate(lines):
            if i == 0:
                chunks.append(line.strip().lstrip(">-").strip())
                continue
            if re.match(r"^[a-zA-Z_-]+:", line):
                break
            chunks.append(line.strip())
        desc = " ".join(c for c in chunks if c)
    return {
        "name": name_m.group(1) if name_m else "",
        "description": desc,
    }


def audit() -> list[Finding]:
    findings: list[Finding] = []

    # Always-on MDCs
    for name in REQUIRED_ALWAYS_ON_MDC:
        rel = f".cursor/rules/{name}"
        path = REPO_ROOT / rel
        if not path.is_file():
            findings.append(Finding("error", "missing_mdc", rel, "Required always-on MDC missing."))
            continue
        text = path.read_text(encoding="utf-8")
        if "alwaysApply: true" not in text:
            findings.append(
                Finding("error", "mdc_not_always_on", rel, "Expected alwaysApply: true.")
            )
        if name == "verification-before-completion.mdc":
            if "fresh verification" not in text.lower() and "FRESH VERIFICATION" not in text:
                findings.append(
                    Finding(
                        "error",
                        "verify_mdc_weak",
                        rel,
                        "Verification MDC missing fresh-evidence language.",
                    )
                )
        if name == "engineering-methodology.mdc":
            for needle in (
                "interview-me",
                "writing-plans",
                "doubt-driven-development",
                "code-review-and-quality",
                "Soft TDD",
                "zero-hop",
            ):
                if needle not in text:
                    findings.append(
                        Finding(
                            "error",
                            "methodology_incomplete",
                            rel,
                            f"Missing expected marker: {needle}",
                        )
                    )

    # Skills
    for skill in REQUIRED_SKILLS:
        rel = f".cursor/skills/{skill}/SKILL.md"
        path = _skill_dir(skill) / "SKILL.md"
        if not path.is_file():
            findings.append(Finding("error", "missing_skill", rel, "Required skill missing."))
            continue
        text = path.read_text(encoding="utf-8")
        lines = text.count("\n") + 1
        if lines > 400:
            findings.append(
                Finding(
                    "error",
                    "skill_too_long",
                    rel,
                    f"Skill has {lines} lines (max 400 for new Nova modules/skills).",
                )
            )
        meta = _parse_frontmatter(text)
        if meta.get("name") != skill:
            findings.append(
                Finding(
                    "error",
                    "skill_name_mismatch",
                    rel,
                    f"Frontmatter name {meta.get('name')!r} != directory {skill!r}.",
                )
            )
        desc = meta.get("description") or ""
        if len(desc) < 40:
            findings.append(
                Finding("error", "weak_description", rel, "description too short for discovery.")
            )
        for marker in REQUIRED_SKILL_MARKERS:
            if marker not in text:
                findings.append(
                    Finding(
                        "warn",
                        "missing_nova_marker",
                        rel,
                        f"Expected Nova guardrail marker {marker!r} in body.",
                    )
                )
        for code, pat, msg in FORBIDDEN_SKILL_PATTERNS:
            if pat.search(text):
                findings.append(Finding("error", code, rel, msg))

        # Process skills must preserve zero-hop (parent session default)
        if "zero-hop" not in text.lower() and "parent session" not in text.lower():
            findings.append(
                Finding(
                    "error",
                    "missing_zero_hop",
                    rel,
                    "Process skill must mention zero-hop or parent-session default.",
                )
            )

    # Index wiring
    agents = _read("AGENTS.md")
    for needle in (
        "engineering-methodology.mdc",
        "verification-before-completion.mdc",
        "interview-me",
        "writing-plans",
        "doubt-driven-development",
        "code-review-and-quality",
        "github-delivery",
        "github-delivery.mdc",
    ):
        if needle not in agents:
            findings.append(
                Finding(
                    "error",
                    "agents_index_gap",
                    "AGENTS.md",
                    f"Constitution index missing {needle!r}.",
                )
            )

    pins = _read(".cursor/skills/SOURCE-PINS.txt")
    for needle in ("obra/superpowers", "addyosmani/agent-skills"):
        if needle not in pins:
            findings.append(
                Finding(
                    "error",
                    "pins_gap",
                    ".cursor/skills/SOURCE-PINS.txt",
                    f"SOURCE-PINS missing lineage {needle!r}.",
                )
            )

    skills_lib = REPO_ROOT / "knowledge/obsidian/00-System/Skills-Library.md"
    if skills_lib.is_file():
        lib_text = skills_lib.read_text(encoding="utf-8")
        for skill in REQUIRED_SKILLS:
            if skill not in lib_text:
                findings.append(
                    Finding(
                        "error",
                        "skills_library_gap",
                        "knowledge/obsidian/00-System/Skills-Library.md",
                        f"Skills-Library missing {skill!r}.",
                    )
                )
    else:
        findings.append(
            Finding(
                "error",
                "skills_library_missing",
                "knowledge/obsidian/00-System/Skills-Library.md",
                "Skills-Library catalog missing.",
            )
        )

    # Conflict: methodology must not fight specialist-routing
    methodology = REPO_ROOT / ".cursor/rules/engineering-methodology.mdc"
    if methodology.is_file():
        mtext = methodology.read_text(encoding="utf-8")
        if "subagent-per-task" not in mtext.lower() and "NOT imported" not in mtext:
            findings.append(
                Finding(
                    "warn",
                    "methodology_import_boundary_unclear",
                    ".cursor/rules/engineering-methodology.mdc",
                    "Clarify that default subagent-per-task is not imported.",
                )
            )

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON findings.")
    args = parser.parse_args(argv)

    findings = audit()
    errors = [f for f in findings if f.severity == "error"]
    warns = [f for f in findings if f.severity == "warn"]

    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        if not findings:
            print("engineering_skills_audit: PASS (0 findings)")
        else:
            for f in findings:
                print(f"{f.severity.upper()}: [{f.code}] {f.path} -- {f.message}")
            print(
                f"engineering_skills_audit: "
                f"{'FAIL' if errors else 'PASS'} "
                f"({len(errors)} error(s), {len(warns)} warn(s))"
            )

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
