"""Nova release version = 0.1.<commit-count>.

Owner: this script (writes VERSION + frontend/package.json).
Invalidation: pre-commit hook before each new commit; pre-push verifies match.

Semver patch is the total commit count on HEAD (after the commit lands).
Major 0 = pre-1.0 product. Minor 1 = Nova app line (bump manually for 2.0 milestones).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = REPO_ROOT / "VERSION"
PACKAGE_JSON = REPO_ROOT / "frontend" / "package.json"
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def git_commit_count() -> int:
    out = subprocess.check_output(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
    )
    return int(out.strip())


def is_amend_commit() -> bool:
    action = os.environ.get("GIT_REFLOG_ACTION", "")
    return "amend" in action.lower()


def target_patch_for_hook() -> int:
    count = git_commit_count()
    if is_amend_commit():
        return count
    return count + 1


def format_version(major: int = 0, minor: int = 1, patch: int = 0) -> str:
    return f"{major}.{minor}.{patch}"


def read_version_file() -> str | None:
    if not VERSION_FILE.is_file():
        return None
    text = VERSION_FILE.read_text(encoding="utf-8").strip()
    return text or None


def write_version_file(version: str) -> None:
    VERSION_FILE.write_text(f"{version}\n", encoding="utf-8")


def read_package_version() -> str | None:
    if not PACKAGE_JSON.is_file():
        return None
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    ver = data.get("version")
    return str(ver).strip() if ver else None


def write_package_version(version: str) -> None:
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    data["version"] = version
    PACKAGE_JSON.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def parse_version(version: str) -> tuple[int, int, int] | None:
    m = SEMVER_RE.match(version.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def sync_version(version: str, *, stage: bool = False) -> bool:
    """Write VERSION + package.json if needed. Returns True when files changed."""
    changed = False
    current_vf = read_version_file()
    if current_vf != version:
        write_version_file(version)
        changed = True
    current_pkg = read_package_version()
    if current_pkg != version:
        write_package_version(version)
        changed = True
    if changed and stage:
        subprocess.run(
            ["git", "add", str(VERSION_FILE), str(PACKAGE_JSON)],
            cwd=REPO_ROOT,
            check=True,
        )
    return changed


def expected_version_for_head() -> str:
    return format_version(patch=git_commit_count())


def expected_version_for_next_commit() -> str:
    return format_version(patch=target_patch_for_hook())


def run_pre_commit() -> int:
    version = expected_version_for_next_commit()
    changed = sync_version(version, stage=True)
    if changed:
        print(f"bump_version: staged {version} (VERSION + frontend/package.json)")
    else:
        print(f"bump_version: already {version}")
    return 0


def run_pre_push() -> int:
    expected = expected_version_for_head()
    vf = read_version_file()
    pkg = read_package_version()
    problems: list[str] = []
    if vf != expected:
        problems.append(f"VERSION is {vf!r}, expected {expected!r}")
    if pkg != expected:
        problems.append(f"frontend/package.json is {pkg!r}, expected {expected!r}")
    if problems:
        print("bump_version: version drift -- run: py -3 tools/bump_version.py --sync")
        for line in problems:
            print(f"  - {line}")
        return 1
    print(f"bump_version: ok ({expected})")
    return 0


def run_sync() -> int:
    version = expected_version_for_head()
    changed = sync_version(version, stage=False)
    print(f"bump_version: {'updated' if changed else 'already'} {version}")
    return 0


def run_show() -> int:
    count = git_commit_count()
    print(f"commits={count}")
    print(f"head={expected_version_for_head()}")
    print(f"next_commit={expected_version_for_next_commit()}")
    vf = read_version_file()
    pkg = read_package_version()
    print(f"VERSION_file={vf}")
    print(f"package_json={pkg}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nova commit-count versioning")
    parser.add_argument(
        "--pre-commit",
        action="store_true",
        help="Bump to next commit count and stage version files",
    )
    parser.add_argument(
        "--pre-push",
        action="store_true",
        help="Verify VERSION matches current commit count",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Align files to current HEAD commit count (no stage)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Print commit count and version fields",
    )
    args = parser.parse_args(argv)
    if args.pre_commit:
        return run_pre_commit()
    if args.pre_push:
        return run_pre_push()
    if args.sync:
        return run_sync()
    if args.show:
        return run_show()
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
