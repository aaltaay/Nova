"""Pure classifiers for repo_hygiene.py -- plain data in, findings out.

No subprocess, no filesystem. The CLI in repo_hygiene.py gathers git state
and hands it here so every decision is unit-testable with literal dicts,
the same split stale_pr_branches.py uses.
"""

from __future__ import annotations

from dataclasses import dataclass

PROTECTED = frozenset({"master", "main", "HEAD"})
STALE_STATES = frozenset({"MERGED", "CLOSED"})
MAX_WORKTREE_AGE_HOURS = 24.0


@dataclass(frozen=True)
class Finding:
    kind: str
    subject: str
    detail: str
    fixable: bool = False


def _pr_state(prs_by_head: dict[str, list[dict]], head: str) -> str | None:
    """OPEN wins over any older closed PR on the same head; None = no PR."""
    prs = prs_by_head.get(head, [])
    if not prs:
        return None
    states = {str(pr.get("state") or "").upper() for pr in prs}
    if "OPEN" in states:
        return "OPEN"
    stale = states & STALE_STATES
    return sorted(stale)[0] if stale else None


def index_prs(prs: list[dict] | None) -> dict[str, list[dict]] | None:
    """Group gh PR rows by head branch. None means gh was unavailable."""
    if prs is None:
        return None
    by_head: dict[str, list[dict]] = {}
    for pr in prs:
        head = str(pr.get("head") or "").strip()
        if head:
            by_head.setdefault(head, []).append(pr)
    return by_head


def classify_local_branches(
    branches: list[dict],
    prs_by_head: dict[str, list[dict]] | None,
) -> list[Finding]:
    """branches: [{name, upstream_gone: bool, checked_out_at: str|None}].

    A branch is fixable only when GitHub says its PR is merged/closed and no
    worktree has it checked out. Without gh data nothing is fixable.
    """
    out: list[Finding] = []
    for br in branches:
        name = str(br.get("name") or "")
        if not name or name in PROTECTED:
            continue
        where = br.get("checked_out_at")
        state = _pr_state(prs_by_head, name) if prs_by_head is not None else None
        if state in STALE_STATES:
            if where:
                out.append(Finding("checked_out_elsewhere", name,
                                   f"PR {state} but checked out at {where}"))
            else:
                out.append(Finding("merged_local_branch", name, f"PR {state}", fixable=True))
        elif state is None:
            if prs_by_head is None:
                out.append(Finding("branch_unknown", name, "gh unavailable; PR state unknown"))
            else:
                gone = " (upstream gone)" if br.get("upstream_gone") else ""
                out.append(Finding("no_pr_branch", name, f"no PR yet{gone}"))
    return out


def classify_worktrees(
    worktrees: list[dict],
    prs_by_head: dict[str, list[dict]] | None,
    master_reachable: set[str],
    now: float,
    max_age_hours: float = MAX_WORKTREE_AGE_HOURS,
) -> list[Finding]:
    """worktrees: [{path, is_main, exists, head, branch: str|None, clean: bool,
    last_activity_ts: float}]. Stale = clean, finished (merged/closed PR or
    detached on origin/master history), and untouched for max_age_hours."""
    out: list[Finding] = []
    for wt in worktrees:
        path = str(wt.get("path") or "")
        if wt.get("is_main"):
            continue
        if not wt.get("exists", True):
            out.append(Finding("worktree_missing", path, "directory gone", fixable=True))
            continue
        if not wt.get("clean", False):
            out.append(Finding("worktree_dirty", path, "uncommitted changes"))
            continue
        branch = wt.get("branch")
        age_h = (now - float(wt.get("last_activity_ts") or now)) / 3600.0
        if branch:
            state = _pr_state(prs_by_head, branch) if prs_by_head is not None else None
            finished = state in STALE_STATES
            why = f"branch {branch} PR {state}" if state else f"branch {branch} has no PR"
        else:
            finished = str(wt.get("head") or "") in master_reachable
            why = "detached on origin/master history" if finished else "detached, not on master"
        if finished and age_h >= max_age_hours:
            out.append(Finding("worktree_stale", path, f"{why}; idle {age_h:.0f}h", fixable=True))
        elif finished:
            out.append(Finding("worktree_recent", path, f"{why}; idle {age_h:.0f}h (<{max_age_hours:.0f}h)"))
        else:
            out.append(Finding("worktree_active", path, why))
    return out


def classify_stashes(stashes: list[dict], now: float) -> list[Finding]:
    """stashes: [{ref, ts, message}]. Never fixable -- a human decides."""
    out: list[Finding] = []
    for st in stashes:
        age_d = (now - float(st.get("ts") or now)) / 86400.0
        out.append(Finding("stash_present", str(st.get("ref") or ""),
                           f"{age_d:.0f}d old: {st.get('message', '')}"))
    return out


def classify_remote_refs(refs: list[str], remotes: list[str]) -> list[Finding]:
    """Remote-tracking refs whose remote is no longer configured."""
    known = set(remotes)
    out: list[Finding] = []
    for ref in refs:
        remote = ref.split("/", 1)[0] if "/" in ref else ""
        if remote and remote not in known:
            out.append(Finding("orphan_remote_ref", ref, f"remote '{remote}' not configured", fixable=True))
    return out


def classify_working_tree(porcelain: list[str]) -> list[Finding]:
    """`git status --porcelain` lines -> dirty/staged/untracked findings."""
    out: list[Finding] = []
    for line in porcelain:
        if len(line) < 4:
            continue
        code, path = line[:2], line[3:]
        if code == "??":
            out.append(Finding("untracked", path, "untracked, not ignored"))
        elif code[0] not in " ?":
            out.append(Finding("staged", path, f"staged ({code.strip()})"))
        else:
            out.append(Finding("dirty_tracked", path, f"modified ({code.strip()})"))
    return out


def classify_stop(state: dict) -> tuple[bool, str]:
    """Claude Stop-hook decision.

    state: {branch: str|None (None = detached), porcelain: [str], ahead: int,
            has_upstream: bool, ahead_of_master: int, stop_hook_active: bool}
    Returns (block, reason). One-shot: a second stop is always allowed.
    """
    if state.get("stop_hook_active"):
        return False, ""
    branch = state.get("branch")
    if not branch:
        return False, ""
    tree = classify_working_tree(list(state.get("porcelain") or []))
    unpushed = int(state.get("ahead") or 0) if state.get("has_upstream") else int(
        state.get("ahead_of_master") or 0
    )
    if not tree and unpushed == 0:
        return False, ""
    parts: list[str] = []
    for kind, label in (("dirty_tracked", "modified"), ("staged", "staged"), ("untracked", "untracked")):
        names = [f.subject for f in tree if f.kind == kind]
        if names:
            parts.append(f"{label}: {', '.join(names[:6])}" + (" ..." if len(names) > 6 else ""))
    if unpushed:
        parts.append(f"{unpushed} commit(s) not on origin")
    if branch in PROTECTED:
        remedy = ("you are on master. Create a branch from origin/master "
                  "(git switch -c <name> origin/master), commit the intentional paths, push, open the PR")
    else:
        remedy = ("commit the intentional paths (git add <paths> && git commit -m 'wip: ...'), "
                  "push (git push -u origin HEAD), and open or refresh the PR")
    reason = (
        f"repo_hygiene stop-gate: turn is ending with {'; '.join(parts)} on branch '{branch}'. "
        f"Finish first: {remedy}. If the user explicitly asked you to stop here, "
        "stop again and say why (workspace-hygiene.mdc)."
    )
    return True, reason


def summarize(findings: list[Finding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.kind] = counts.get(f.kind, 0) + 1
    return counts
