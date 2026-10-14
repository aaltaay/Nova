"""The tracked pre-push hook refuses a push that rewrites a branch (AGENTS.md section 5.1; owner, 2026-10-14:
"Force push, meaning we're deleting work. Everything needs to be merged properly").

No test pushes anything, to anywhere. Each one runs the hook the way git does -- the remote's name and URL as
arguments, one ``<local ref> <local sha> <remote ref> <remote sha>`` line per ref on stdin -- inside a temp repo
whose commits stand for the two sides: a new branch, a fast-forward and a delete pass; a rewrite (what
``--force``, ``--force-with-lease`` or ``+ref`` sends after a rebase or amend) is refused.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".githooks" / "pre-push"
ZERO = "0" * 40


def _sh() -> str:
    found = shutil.which("sh")
    if found:
        return found
    git_root = Path(subprocess.check_output(["git", "--exec-path"], text=True).strip()).parents[2]
    bundled = git_root / "usr" / "bin" / "sh.exe"          # Git for Windows
    if bundled.exists():
        return str(bundled)
    pytest.fail("no sh to run the hook with")


@pytest.fixture()
def repo(tmp_path):
    def git(*args):
        return subprocess.run(["git", "-c", "user.name=Hook test", "-c", "user.email=hook@example.invalid",
                               *args], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()

    git("init", "--initial-branch=master")
    git("commit", "--allow-empty", "-m", "base")
    base = git("rev-parse", "HEAD")
    git("commit", "--allow-empty", "-m", "work")
    pushed = git("rev-parse", "HEAD")                     # what origin has
    git("commit", "--allow-empty", "-m", "more work")
    ahead = git("rev-parse", "HEAD")                      # a fast-forward of it
    git("reset", "--hard", base)
    git("commit", "--allow-empty", "-m", "work, rewritten")
    rewritten = git("rev-parse", "HEAD")                  # an amend / rebase of it
    return tmp_path, {"base": base, "pushed": pushed, "ahead": ahead, "rewritten": rewritten}


def run_hook(cwd: Path, *lines: str) -> subprocess.CompletedProcess:
    # Bytes, LF-terminated, as git writes them (text mode would turn each \n into \r\n on Windows).
    result = subprocess.run([_sh(), str(HOOK), "origin", "https://github.com/aaltaay/Nova.git"],
                            input="".join(f"{line}\n" for line in lines).encode(), cwd=cwd, capture_output=True,
                            env=dict(os.environ))
    return subprocess.CompletedProcess(result.args, result.returncode, result.stdout.decode(errors="replace"),
                                       result.stderr.decode(errors="replace"))


def test_a_crlf_line_reads_the_same_as_an_lf_one(repo):
    cwd, c = repo
    result = subprocess.run([_sh(), str(HOOK), "origin", "u"], cwd=cwd, capture_output=True,
                            input=f"refs/heads/x {c['ahead']} refs/heads/x {c['pushed']}\r\n".encode())
    assert result.returncode == 0


def test_a_new_branch_a_fast_forward_and_a_delete_pass(repo):
    cwd, c = repo
    assert run_hook(cwd, f"refs/heads/x {c['pushed']} refs/heads/x {ZERO}").returncode == 0
    assert run_hook(cwd, f"refs/heads/x {c['ahead']} refs/heads/x {c['pushed']}").returncode == 0
    assert run_hook(cwd, f"(delete) {ZERO} refs/heads/x {c['pushed']}").returncode == 0


def test_a_rewrite_is_refused_and_says_to_merge(repo):
    cwd, c = repo
    result = run_hook(cwd, f"refs/heads/x {c['rewritten']} refs/heads/x {c['pushed']}")
    assert result.returncode == 1
    assert "push refused" in result.stderr and "never force-pushes" in result.stderr
    assert "git merge" in result.stderr


def test_one_rewritten_ref_refuses_the_whole_push(repo):
    cwd, c = repo
    result = run_hook(cwd, f"refs/heads/ok {c['ahead']} refs/heads/ok {c['pushed']}",
                      f"refs/heads/x {c['rewritten']} refs/heads/x {c['pushed']}")
    assert result.returncode == 1 and "'x'" in result.stderr and "'ok'" not in result.stderr


def test_a_remote_tip_it_cannot_see_is_refused(repo):
    # The remote moved and was never fetched: the push cannot be proved a fast-forward.
    cwd, c = repo
    assert run_hook(cwd, f"refs/heads/x {c['ahead']} refs/heads/x {'e' * 40}").returncode == 1


def test_tags_are_not_this_hooks_business(repo):
    cwd, c = repo
    assert run_hook(cwd, f"refs/tags/v1 {c['rewritten']} refs/tags/v1 {c['pushed']}").returncode == 0


@pytest.mark.parametrize(("guard_exit", "hook_exit"), [(1, 1), (0, 0), (2, 0)])
def test_the_push_guard_gets_the_same_lines_and_only_its_refusal_stops_the_push(repo, guard_exit, hook_exit):
    # PR #958's guard (repo_hygiene.py push-guard): 1 refuses; 0 passes; 2 (a copy without it) fails open.
    cwd, c = repo
    tools = cwd / "tools"
    tools.mkdir()
    seen = cwd / "seen.txt"
    (tools / "repo_hygiene.py").write_text(
        "import sys, pathlib\n"
        f"pathlib.Path({str(seen)!r}).write_text(' '.join(sys.argv[1:]) + '|' + sys.stdin.read())\n"
        f"print('push-guard: said {guard_exit}', file=sys.stderr)\n"
        f"sys.exit({guard_exit})\n", encoding="utf-8")
    line = f"refs/heads/x {c['ahead']} refs/heads/x {c['pushed']}"
    result = run_hook(cwd, line)
    assert result.returncode == hook_exit
    args, stdin = seen.read_text().split("|", 1)
    assert args == "push-guard origin https://github.com/aaltaay/Nova.git" and line in stdin
    if guard_exit == 1:
        assert "push-guard: said 1" in result.stderr
