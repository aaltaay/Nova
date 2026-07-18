"""Light / REM / Deep dream phases + orchestration."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_dream_lib.parse import (
    RUN_LOG_CAP,
    AgentMemory,
    PendingFact,
    append_promotion_to_spec,
    is_promotable,
    load_agent_memory,
    remove_pending_facts,
    stamp_last_dream,
    trim_run_log_text,
)
from agent_dream_lib.report import (
    DreamReport,
    StagedAgent,
    append_diary,
    format_diary,
    report_text,
)

STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "when",
    "that",
    "this",
    "from",
    "into",
    "not",
    "is",
    "are",
    "be",
    "as",
    "at",
    "by",
    "it",
    "its",
    "via",
    "only",
    "also",
    "than",
    "then",
    "over",
    "under",
    "after",
    "before",
    "about",
    "out",
    "no",
    "yes",
}

__all__ = ["DreamReport", "StagedAgent", "run_dream", "report_text"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def _rel(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def load_registry_agents(registry: dict, repo_root: Path) -> list[AgentMemory]:
    out: list[AgentMemory] = []
    for entry in registry.get("agents") or []:
        aid = entry.get("id") or entry.get("name")
        if not aid:
            continue
        mem = repo_root / (entry.get("memory") or f".cursor/agent-memory/{aid}-memory.md")
        spec = repo_root / (entry.get("spec") or f".cursor/agents/{aid}.md")
        out.append(load_agent_memory(aid, mem, spec))
    return out


def phase_light(memories: list[AgentMemory], repo_root: Path) -> list[StagedAgent]:
    staged: list[StagedAgent] = []
    for mem in memories:
        spec_text = mem.spec_path.read_text(encoding="utf-8") if mem.spec_path.is_file() else ""
        promotable: list[dict[str, str]] = []
        rejected: list[dict[str, str]] = []
        for fact in mem.pending_facts:
            ok, reason = is_promotable(fact, spec_text)
            row = {"text": fact.text, "raw_line": fact.raw_line, "reason": reason}
            (promotable if ok else rejected).append(row)
        staged.append(
            StagedAgent(
                agent_id=mem.agent_id,
                memory_rel=_rel(repo_root, mem.memory_path),
                spec_rel=_rel(repo_root, mem.spec_path),
                open_backlog_count=len(mem.open_backlog),
                pending_count=len(mem.pending_facts),
                run_log_count=len(mem.run_log_entries),
                promotable=promotable,
                rejected=rejected,
                learnings_sample=mem.learnings[:8],
            )
        )
    return staged


def phase_rem(staged: list[StagedAgent], top_n: int = 8) -> list[dict[str, Any]]:
    tokens: Counter[str] = Counter()
    sources: list[str] = []
    for s in staged:
        for text in s.learnings_sample + [p["text"] for p in s.promotable]:
            sources.append(text)
            for tok in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower()):
                if tok not in STOPWORDS:
                    tokens[tok] += 1
    themes: list[dict[str, Any]] = []
    for word, count in tokens.most_common(top_n):
        if count < 2:
            continue
        themes.append({"theme": word, "count": count})
    if not themes and sources:
        themes.append({"theme": "sparse_signal", "count": len(sources)})
    return themes


def phase_deep(
    memories: list[AgentMemory],
    staged: list[StagedAgent],
    repo_root: Path,
    *,
    write: bool,
    when: str,
) -> tuple[list[dict[str, str]], list[dict[str, Any]], list[str]]:
    by_id = {m.agent_id: m for m in memories}
    promotions: list[dict[str, str]] = []
    trims: list[dict[str, Any]] = []
    touched: list[str] = []

    for s in staged:
        mem = by_id[s.agent_id]
        mem_text = mem.text
        spec_text = mem.spec_path.read_text(encoding="utf-8") if mem.spec_path.is_file() else ""
        promoted_raw: list[str] = []
        for p in s.promotable:
            fact = PendingFact(text=p["text"], raw_line=p["raw_line"])
            ok, reason = is_promotable(fact, spec_text)
            if not ok:
                continue
            promotions.append(
                {
                    "agent_id": s.agent_id,
                    "text": fact.text,
                    "target": s.spec_rel,
                    "reason": reason,
                }
            )
            if write:
                spec_text = append_promotion_to_spec(spec_text, fact.text, s.agent_id)
                promoted_raw.append(fact.raw_line)

        new_mem = mem_text
        if write and promoted_raw:
            new_mem = remove_pending_facts(new_mem, promoted_raw)

        trimmed_text, removed = trim_run_log_text(new_mem, RUN_LOG_CAP)
        if removed:
            trims.append({"agent_id": s.agent_id, "removed": removed, "cap": RUN_LOG_CAP})
            new_mem = trimmed_text

        if write and (promoted_raw or removed):
            new_mem = stamp_last_dream(new_mem, when)
            mem.spec_path.write_text(spec_text, encoding="utf-8", newline="\n")
            mem.memory_path.write_text(new_mem, encoding="utf-8", newline="\n")
            touched.append(s.spec_rel)
            touched.append(s.memory_rel)

    return promotions, trims, touched


def run_dream(
    registry: dict,
    repo_root: Path,
    *,
    agent_filter: str | None = None,
    phase: str = "all",
    write: bool = False,
    diary_path: Path | None = None,
    llm_rem: bool = True,
    obsidian: bool = False,
    pinecone: bool = False,
    pinecone_official: bool = False,
    pinecone_full: bool = False,
    bridges: bool = False,
    commit: bool = False,
    push: bool = False,
) -> DreamReport:
    from agent_dream_lib.bridges import enable_claude_auto_dream, export_openclaw_memory
    from agent_dream_lib.git_ship import ship_dream_changes
    from agent_dream_lib.obsidian import apply_obsidian_hygiene
    from agent_dream_lib.pinecone_bridge import run_pinecone_ingest
    from agent_dream_lib.rem_llm import run_llm_rem

    phase = phase.lower().strip()
    if phase not in {"light", "rem", "deep", "all"}:
        raise ValueError(f"invalid phase: {phase}")
    if push and not commit:
        raise ValueError("--push requires --commit")
    if commit and not write:
        raise ValueError("--commit requires --write")

    when = _now_iso()
    memories = load_registry_agents(registry, repo_root)
    if agent_filter and agent_filter.lower() != "all":
        memories = [m for m in memories if m.agent_id == agent_filter]
        if not memories:
            raise ValueError(f"unknown agent id: {agent_filter}")

    report = DreamReport(phase=phase, dry_run=not write, captured_at=when)
    staged = phase_light(memories, repo_root)
    report.agents = staged

    if phase in {"rem", "all"}:
        report.themes = phase_rem(staged)
        samples: list[str] = []
        for s in staged:
            samples.extend(s.learnings_sample)
            samples.extend(p["text"] for p in s.promotable)
        if llm_rem:
            narrative, mode = run_llm_rem(report.themes, samples, repo_root)
            report.rem_mode = mode
            if narrative:
                report.rem_narrative = narrative
            else:
                report.rem_narrative = (
                    "Heuristic REM: themes "
                    + ", ".join(t["theme"] for t in report.themes[:8])
                    + ". Promote only scored pending facts; prune WIP noise."
                )
        else:
            report.rem_mode = "heuristic"
            report.rem_narrative = (
                "Heuristic REM (LLM disabled): "
                + ", ".join(t["theme"] for t in report.themes[:8])
            )

    if phase in {"deep", "all"}:
        promotions, trims, touched = phase_deep(
            memories, staged, repo_root, write=write, when=when
        )
        report.promotions = promotions
        report.run_logs_trimmed = trims
        report.files_touched.extend(touched)

    if obsidian and phase in {"deep", "all", "rem"}:
        obs = apply_obsidian_hygiene(repo_root, write=write, when=when[:10])
        report.obsidian = {
            "notes_scanned": obs.notes_scanned,
            "findings_count": len(obs.findings),
            "findings": [
                {"path": f.path, "kind": f.kind, "detail": f.detail} for f in obs.findings
            ],
        }
        report.files_touched.extend(obs.files_touched)

    if bridges and phase in {"rem", "deep", "all"}:
        summaries = [
            f"{a.agent_id}: pending={a.pending_count} "
            f"promotable={len(a.promotable)} backlog={a.open_backlog_count}"
            for a in staged
        ]
        claude = enable_claude_auto_dream(repo_root, write=write)
        oc = export_openclaw_memory(repo_root, summaries, write=write)
        report.bridges = {
            "actions": claude.actions + oc.actions,
            "files": claude.files_touched + oc.files_touched,
        }
        report.files_touched.extend(claude.files_touched + oc.files_touched)

    if pinecone and phase in {"deep", "all"}:
        pc = run_pinecone_ingest(
            repo_root,
            write=write,
            official_transcripts=pinecone_official,
            limit=None if pinecone_full else 5,
        )
        report.pinecone = {
            "ran": pc.ran,
            "dry_run": pc.dry_run,
            "exit_code": pc.exit_code,
            "command": pc.command,
            "summary": pc.summary,
        }

    if phase in {"rem", "deep", "all"}:
        diary = diary_path or (repo_root / ".cursor" / "agent-system" / "DREAMS.md")
        body = format_diary(report)
        if phase == "rem":
            labeled = "## REM\n\n" + body + "\n"
        elif phase == "deep":
            labeled = "## Deep Sleep\n\n" + body + "\n"
        else:
            labeled = "## REM\n\n" + body + "\n## Deep Sleep\n\n" + body + "\n"
        report.diary_appended = append_diary(diary, labeled, write=write)
        if report.diary_appended:
            report.files_touched.append(_rel(repo_root, diary))

    if commit:
        git = ship_dream_changes(
            repo_root,
            list(dict.fromkeys(report.files_touched)),
            commit=True,
            push=push,
        )
        report.git = {
            "committed": git.committed,
            "pushed": git.pushed,
            "sha": git.sha,
            "detail": git.detail,
        }

    return report
