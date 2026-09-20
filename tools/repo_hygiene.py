#!/usr/bin/env python3
"""Is this clone clean? Report, and fix the safe class of local git debt.

Every other gate (stale_pr_branches.py, pr-delivery.yml, CI) looks at GitHub
or at file text. Nothing looked at the clone itself, so merged local branches,
abandoned worktrees, orphan remote-tracking refs, stashes and dirty trees piled
up unseen. This tool looks at the clone.

`fix` touches only the safe class: prune, orphan remote-tracking refs, clean
worktrees on finished branches idle >24h, and local branches whose PR GitHub
says is merged/closed (never by ancestry -- squash merges hide it). Stashes,
dirty files and branches without a PR are reported, never touched. If `gh`
is unavailable nothing branch- or worktree-related is fixable.

Usage:
  py -3 tools/repo_hygiene.py status [--json]
  py -3 tools/repo_hygiene.py fix [--dry-run] [--max-age-hours 24]
  py -3 tools/repo_hygiene.py stop-gate      # Claude Code Stop hook (stdin JSON)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from repo_hygiene_lib import (  # noqa: E402
    Finding,
    classify_local_branches,
    classify_remote_refs,
    classify_stashes,
    classify_stop,
    classify_working_tree,
    classify_worktrees,
    index_prs,
    summarize,
)

GH_TIMEOUT_SEC = 8
EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_FAILED = 2
MAX_FIX_PASSES = 2
FIXABLE_ORDER = ("worktree_missing", "orphan_remote_ref", "worktree_stale", "merged_local_branch")


def _git(*args: str, cwd: str | None = None) -> str:
    # Strip only line endings: a leading space is significant in
    # `status --porcelain` (" M path" = modified, unstaged).
    return subprocess.check_output(["git", *args], text=True, cwd=cwd,
                                   stderr=subprocess.DEVNULL).strip("\r\n")


def _git_ok(*args: str, cwd: str | None = None) -> bool:
    return subprocess.run(["git", *args], cwd=cwd, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0


def _gh_prs() -> list[dict] | None:
    """PR rows via stale_pr_branches; None when gh is missing/offline/unauthenticated."""
    try:
        from stale_pr_branches import _gh_all_prs  # noqa: E402

        return _gh_all_prs()
    except Exception:
        return None


# --- gather -----------------------------------------------------------------

def _worktrees() -> list[dict]:
    raw = _git("worktree", "list", "--porcelain")
    items: list[dict] = []
    cur: dict = {}
    for line in raw.splitlines() + [""]:
        if not line:
            if cur:
                items.append(cur)
            cur = {}
            continue
        key, _, val = line.partition(" ")
        if key == "worktree":
            cur = {"path": val, "branch": None, "head": ""}
        elif key == "HEAD":
            cur["head"] = val
        elif key == "branch":
            cur["branch"] = val.replace("refs/heads/", "", 1)
    for i, wt in enumerate(items):
        p = Path(wt["path"])
        wt["is_main"] = i == 0
        wt["exists"] = p.is_dir()
        if wt["exists"] and not wt["is_main"]:
            try:
                wt["clean"] = _git("status", "--porcelain", cwd=wt["path"]) == ""
                commit_ts = float(_git("log", "-1", "--format=%ct", cwd=wt["path"]) or 0)
            except subprocess.CalledProcessError:
                wt["clean"], commit_ts = False, 0.0
            wt["last_activity_ts"] = max(p.stat().st_mtime, commit_ts)
    return items


def _local_branches(worktrees: list[dict]) -> list[dict]:
    checked = {wt["branch"]: wt["path"] for wt in worktrees if wt.get("branch")}
    raw = _git("for-each-ref", "refs/heads",
               "--format=%(refname:short)%09%(upstream:track)")
    out = []
    for line in raw.splitlines():
        name, _, track = line.partition("\t")
        out.append({"name": name, "upstream_gone": track.strip() == "[gone]",
                    "checked_out_at": checked.get(name)})
    return out


def _stashes() -> list[dict]:
    raw = _git("stash", "list", "--format=%gd%x09%ct%x09%gs")
    out = []
    for line in raw.splitlines():
        ref, ts, msg = (line.split("\t", 2) + ["", ""])[:3]
        out.append({"ref": ref, "ts": float(ts or 0), "message": msg})
    return out


def _master_reachable(worktrees: list[dict]) -> set[str]:
    heads = {wt["head"] for wt in worktrees if not wt.get("branch") and wt.get("head")}
    return {h for h in heads if _git_ok("merge-base", "--is-ancestor", h, "origin/master")}


def gather(max_age_hours: float) -> tuple[list[Finding], bool]:
    """All findings for this clone plus whether gh data was available."""
    now = time.time()
    prs_by_head = index_prs(_gh_prs())
    wts = _worktrees()
    findings: list[Finding] = []
    findings += classify_worktrees(wts, prs_by_head, _master_reachable(wts), now, max_age_hours)
    findings += classify_local_branches(_local_branches(wts), prs_by_head)
    findings += classify_remote_refs(
        _git("for-each-ref", "refs/remotes", "--format=%(refname:short)").splitlines(),
        _git("remote").splitlines(),
    )
    findings += classify_stashes(_stashes(), now)
    findings += classify_working_tree(_git("status", "--porcelain").splitlines())
    return findings, prs_by_head is not None


# --- commands ----------------------------------------------------------------

def _print_report(findings: list[Finding], gh_ok: bool) -> None:
    if not findings and gh_ok:
        print("repo_hygiene: OK (clean clone)")
        return
    print("repo_hygiene: findings" + ("" if gh_ok else " (gh unavailable: PR-based fixes disabled)"))
    for f in findings:
        flag = "FIX " if f.fixable else "    "
        print(f"  {flag}{f.kind:<22} {f.subject}  -- {f.detail}")
    fixable = [f for f in findings if f.fixable]
    if fixable:
        print(f"Run: py -3 tools/repo_hygiene.py fix   ({len(fixable)} safe action(s); --dry-run to preview)")


def cmd_status(args: argparse.Namespace) -> int:
    try:
        findings, gh_ok = gather(args.max_age_hours)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"repo_hygiene: FAILED inspection ({type(exc).__name__})", file=sys.stderr)
        return EXIT_FAILED
    if args.json:
        print(json.dumps({"gh": gh_ok, "counts": summarize(findings),
                          "findings": [asdict(f) for f in findings]}, indent=2))
    else:
        _print_report(findings, gh_ok)
    return EXIT_FAILED if not gh_ok else EXIT_FINDINGS if findings else EXIT_CLEAN


def _apply(f: Finding, dry: bool) -> tuple[bool, str]:
    if f.kind == "worktree_missing":
        cmd = ["git", "worktree", "prune"]
    elif f.kind == "orphan_remote_ref":
        cmd = ["git", "update-ref", "-d", f"refs/remotes/{f.subject}"]
    elif f.kind == "worktree_stale":
        cmd = ["git", "worktree", "remove", f.subject]
    elif f.kind == "merged_local_branch":
        cmd = ["git", "branch", "-D", f.subject]
    else:
        return False, f"skip {f.kind} {f.subject}"
    shown = " ".join(cmd)
    if dry:
        return True, f"would run: {shown}"
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.returncode == 0, (
        f"{'ok' if res.returncode == 0 else 'FAILED'}: {shown}" +
        ("" if res.returncode == 0 else f"  ({res.stderr.strip()})"))


def cmd_fix(args: argparse.Namespace) -> int:
    try:
        if not args.dry_run:
            fetched = subprocess.run(
                ["git", "fetch", "--prune", "origin"], capture_output=True, text=True)
            if fetched.returncode:
                print("repo_hygiene: FAILED fetch; cleanup not attempted", file=sys.stderr)
                return EXIT_FAILED
        findings, gh_ok = gather(args.max_age_hours)
        for _ in range(MAX_FIX_PASSES):
            if not gh_ok:
                print("repo_hygiene: FAILED inspection (GitHub unavailable)", file=sys.stderr)
                return EXIT_FAILED
            fixable = sorted((f for f in findings if f.fixable),
                             key=lambda f: FIXABLE_ORDER.index(f.kind))
            if not fixable:
                break
            for finding in fixable:
                ok, message = _apply(finding, args.dry_run)
                print("  " + message)
                if not ok:
                    return EXIT_FAILED
            if args.dry_run:
                break
            # Removing a worktree can expose an unused branch on this next pass.
            findings, gh_ok = gather(args.max_age_hours)
        _print_report(findings, gh_ok)
        return EXIT_FAILED if not gh_ok else EXIT_FINDINGS if findings else EXIT_CLEAN
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"repo_hygiene: FAILED inspection/action ({type(exc).__name__})", file=sys.stderr)
        return EXIT_FAILED


def _stop_state(stop_hook_active: bool) -> dict | None:
    if not _git_ok("rev-parse", "--is-inside-work-tree"):
        return None
    branch = _git("symbolic-ref", "--short", "-q", "HEAD") if _git_ok("symbolic-ref", "-q", "HEAD") else None
    has_upstream = _git_ok("rev-parse", "--abbrev-ref", "@{u}")
    return {
        "branch": branch,
        "porcelain": _git("status", "--porcelain").splitlines(),
        "has_upstream": has_upstream,
        "ahead": int(_git("rev-list", "--count", "@{u}..HEAD") or 0) if has_upstream else 0,
        "ahead_of_master": int(_git("rev-list", "--count", "origin/master..HEAD") or 0)
        if _git_ok("rev-parse", "origin/master") else 0,
        "stop_hook_active": stop_hook_active,
    }


def cmd_stop_gate(_args: argparse.Namespace) -> int:
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        payload = {}
    try:
        state = _stop_state(bool(payload.get("stop_hook_active")))
        if state is None:
            return 0
        block, reason = classify_stop(state)
    except Exception:
        return 0  # fail-open: a broken hook must never trap a session
    if block:
        print(reason, file=sys.stderr)
        return 2
    return 0


def format_session_brief_lines() -> list[str]:
    """One line for session-start briefs (Cursor + Claude). Fail-open."""
    try:
        findings, gh_ok = gather(24.0)
    except Exception:
        return []
    if not findings:
        return ["Repo hygiene: OK (clean clone)."]
    c = summarize(findings)
    bits = [f"{n} {k.replace('_', ' ')}" for k, n in sorted(c.items())]
    fixable = sum(1 for f in findings if f.fixable)
    tail = f"; {fixable} safe fix(es): `py -3 tools/repo_hygiene.py fix`" if fixable else ""
    return ["Repo hygiene: " + ", ".join(bits) + tail
            + ("" if gh_ok else " (gh unavailable)") + " -- `py -3 tools/repo_hygiene.py status`."]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p_status = sub.add_parser("status", help="report local debt")
    p_status.add_argument("--json", action="store_true")
    p_status.add_argument("--max-age-hours", type=float, default=24.0)
    p_status.set_defaults(func=cmd_status)
    p_fix = sub.add_parser("fix", help="apply the safe class of fixes")
    p_fix.add_argument("--dry-run", action="store_true")
    p_fix.add_argument("--max-age-hours", type=float, default=24.0)
    p_fix.set_defaults(func=cmd_fix)
    p_stop = sub.add_parser("stop-gate", help="Claude Code Stop hook")
    p_stop.set_defaults(func=cmd_stop_gate)
    args = parser.parse_args(argv)
    os.chdir(Path(os.getcwd()))
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
