"""Delivery, constitution index, and lineage checks for engineering_skills_audit.

Extracted from ``tools/engineering_skills_audit.py`` so both modules stay
well under the 400-line soft limit.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable


def audit_delivery_and_index(
    repo_root: Path,
    read_fn: Callable[[str], str],
    finding_cls: type,
    required_skills: tuple[str, ...],
) -> list:
    findings: list = []

    delivery_mdc = read_fn(".cursor/rules/github-delivery.mdc")
    if "delete the head branch" not in delivery_mdc.lower():
        findings.append(
            finding_cls(
                "error",
                "missing_delete_head_branch",
                ".cursor/rules/github-delivery.mdc",
                "Always-on delivery rule must require deleting the PR head branch after merge or close.",
            )
        )
    if "master branch protection" not in delivery_mdc.lower():
        findings.append(
            finding_cls(
                "error",
                "missing_master_branch_protection",
                ".cursor/rules/github-delivery.mdc",
                "Always-on delivery rule must require master branch protection (no force-push/delete, required CI).",
            )
        )
    if "merges ready prs" not in delivery_mdc.lower():
        findings.append(
            finding_cls(
                "error",
                "missing_auto_merge_ready_prs",
                ".cursor/rules/github-delivery.mdc",
                "Always-on delivery rule must say GitHub Actions merges ready PRs (no wait for a human merge ask).",
            )
        )
    if "origin/master" not in delivery_mdc.lower():
        findings.append(
            finding_cls(
                "error",
                "missing_clean_start_origin_master",
                ".cursor/rules/github-delivery.mdc",
                "Always-on delivery rule must require a clean start from origin/master.",
            )
        )
    if "quick fix" not in delivery_mdc.lower():
        findings.append(
            finding_cls(
                "error",
                "missing_prompt_priority_override",
                ".cursor/rules/github-delivery.mdc",
                "Always-on delivery rule must say casual phrasing such as 'quick fix' does not waive the gates.",
            )
        )
    board_url = "https://github.com/users/aaltaay/projects/1"
    if board_url not in delivery_mdc:
        findings.append(
            finding_cls(
                "error",
                "missing_nova_delivery_board",
                ".cursor/rules/github-delivery.mdc",
                "Always-on delivery rule must name the canonical Nova Delivery board URL.",
            )
        )
    if "gh project item-add" not in delivery_mdc:
        findings.append(
            finding_cls(
                "error",
                "missing_nova_delivery_item_add",
                ".cursor/rules/github-delivery.mdc",
                "Always-on delivery rule must require `gh project item-add` when the token allows.",
            )
        )
    delivery_skill = read_fn(".cursor/skills/github-delivery/SKILL.md")
    if board_url not in delivery_skill or "gh project item-add" not in delivery_skill:
        findings.append(
            finding_cls(
                "error",
                "missing_nova_delivery_skill_board",
                ".cursor/skills/github-delivery/SKILL.md",
                "github-delivery skill must name the Nova Delivery board and item-add command.",
            )
        )

    finish_mdc = read_fn(".cursor/rules/commit-push-deploy.mdc")
    if "origin/master" not in finish_mdc.lower():
        findings.append(
            finding_cls(
                "error",
                "missing_commit_push_clean_start",
                ".cursor/rules/commit-push-deploy.mdc",
                "Always-on commit/push rule must require a clean start from origin/master.",
            )
        )
    if "ready (non-draft)" not in finish_mdc.lower():
        findings.append(
            finding_cls(
                "error",
                "missing_commit_push_ready_pr",
                ".cursor/rules/commit-push-deploy.mdc",
                "Always-on commit/push rule must require a ready (non-draft) PR as the finish line.",
            )
        )

    # Index wiring
    agents = read_fn("AGENTS.md")
    for needle in (
        "engineering-methodology.mdc",
        "verification-before-completion.mdc",
        "interview-me",
        "writing-plans",
        "doubt-driven-development",
        "code-review-and-quality",
        "github-delivery",
        "github-delivery.mdc",
        "Session lifecycle (Deliver)",
        "origin/master",
        "https://github.com/users/aaltaay/projects/1",
    ):
        if needle not in agents:
            findings.append(
                finding_cls(
                    "error",
                    "agents_index_gap",
                    "AGENTS.md",
                    f"Constitution index missing {needle!r}.",
                )
            )

    pins = read_fn(".cursor/skills/SOURCE-PINS.txt")
    for needle in ("obra/superpowers", "addyosmani/agent-skills"):
        if needle not in pins:
            findings.append(
                finding_cls(
                    "error",
                    "pins_gap",
                    ".cursor/skills/SOURCE-PINS.txt",
                    f"SOURCE-PINS missing lineage {needle!r}.",
                )
            )

    skills_lib = repo_root / "knowledge/obsidian/00-System/Skills-Library.md"
    if skills_lib.is_file():
        lib_text = skills_lib.read_text(encoding="utf-8")
        for skill in required_skills:
            if skill not in lib_text:
                findings.append(
                    finding_cls(
                        "error",
                        "skills_library_gap",
                        "knowledge/obsidian/00-System/Skills-Library.md",
                        f"Skills-Library missing {skill!r}.",
                    )
                )
    else:
        findings.append(
            finding_cls(
                "error",
                "skills_library_missing",
                "knowledge/obsidian/00-System/Skills-Library.md",
                "Skills-Library catalog missing.",
            )
        )

    # Conflict: methodology must not fight specialist-routing
    methodology = repo_root / ".cursor/rules/engineering-methodology.mdc"
    if methodology.is_file():
        mtext = methodology.read_text(encoding="utf-8")
        if "subagent-per-task" not in mtext.lower() and "NOT imported" not in mtext:
            findings.append(
                finding_cls(
                    "warn",
                    "methodology_import_boundary_unclear",
                    ".cursor/rules/engineering-methodology.mdc",
                    "Clarify that default subagent-per-task is not imported.",
                )
            )

    return findings
