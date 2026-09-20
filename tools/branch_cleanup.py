"""Current-tip proof and conditional deletion for closed PR heads (#369)."""

from __future__ import annotations

import json
import subprocess
import sys
from urllib.parse import quote

PROTECTED_HEADS = frozenset({"master", "main", "HEAD"})


def contained_tip(ref: str, *, cwd: str | None = None) -> str | None:
    """Return the immutable tip only when master contains it; errors propagate."""
    tip = subprocess.check_output(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], text=True, cwd=cwd,
        stderr=subprocess.PIPE,
    ).strip()
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", tip, "refs/remotes/origin/master"],
        cwd=cwd, capture_output=True, text=True,
    )
    if result.returncode not in (0, 1):
        raise subprocess.CalledProcessError(result.returncode, result.args, stderr=result.stderr)
    return tip if result.returncode == 0 else None


def delete_closed_head(gh, repo: str, ref: str, *, same_repo: bool) -> int:
    """Fail closed and lease the verified SHA; never issue an unconditional DELETE."""
    if not same_repo or not ref or ref in PROTECTED_HEADS:
        print(f"skip delete {ref}: protected or fork")
        return 0
    valid = subprocess.run(
        ["git", "check-ref-format", f"refs/heads/{ref}"], capture_output=True, text=True,
    )
    if valid.returncode:
        print(f"refuse delete {ref}: invalid branch", file=sys.stderr)
        return 1
    try:
        result = gh([
            "pr", "list", "--repo", repo, "--state", "all", "--head", ref,
            "--limit", "200", "--json", "state,headRefName,headRepository,headRepositoryOwner",
        ], check=False)
        if result.returncode:
            raise ValueError("PR lookup failed")
        prs = json.loads(result.stdout)
        # Fork heads may share the same short name; they cannot authorize deletion.
        prs = [p for p in prs if p.get("headRefName") == ref and (
            f"{(p.get('headRepositoryOwner') or {}).get('login', '')}/"
            f"{(p.get('headRepository') or {}).get('name', '')}"
        ).lower() == repo.lower()]
        if any(p.get("state") == "OPEN" for p in prs):
            print(f"skip delete {ref}: open_pr")
            return 0
        if not any(p.get("state") in {"MERGED", "CLOSED"} for p in prs):
            print(f"skip delete {ref}: no closed same-repo PR")
            return 0
        result = gh(["api", f"repos/{repo}/git/ref/heads/{quote(ref, safe='')}"], check=False)
        if result.returncode and "HTTP 404" in result.stderr:
            print(f"already absent: {ref}")
            return 0
        if result.returncode:
            raise ValueError("branch lookup failed")
        tip = json.loads(result.stdout)["object"]["sha"]
        result = gh(["api", f"repos/{repo}/compare/master...{tip}"], check=False)
        if result.returncode:
            raise ValueError("master ancestry lookup failed")
        comparison = json.loads(result.stdout)
        if (comparison.get("status") not in {"behind", "identical"} or
                (comparison.get("merge_base_commit") or {}).get("sha") != tip):
            print(f"REFUSE delete {ref}: tip {tip} is not contained in master; "
                  "unmerged/recreated or squash-only work needs review", file=sys.stderr)
            return 1
        # Check OPEN again after network reads. The lease protects concurrent pushes.
        result = gh(["pr", "list", "--repo", repo, "--state", "open", "--head", ref,
                     "--json", "number"], check=False)
        if result.returncode:
            raise ValueError("open PR recheck failed")
        if json.loads(result.stdout):
            print(f"skip delete {ref}: open_pr")
            return 0
        result = subprocess.run([
            "git", "push", f"--force-with-lease=refs/heads/{ref}:{tip}",
            f"https://github.com/{repo}.git", f":refs/heads/{ref}",
        ], capture_output=True, text=True)
        if result.returncode:
            print(f"REFUSE delete {ref}: conditional push failed; branch retained. "
                  f"{result.stderr.strip()}", file=sys.stderr)
            return 1
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as exc:
        print(f"REFUSE delete {ref}: unable to prove safety ({exc})", file=sys.stderr)
        return 1
    print(f"deleted {ref} at verified tip {tip}")
    return 0
