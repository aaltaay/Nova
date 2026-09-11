"""Nova release identity = vNNN (commit count from the first commit).

Public tag / VERSION file: v001, v042, v473, v1000 (at least three digits).
electron-builder still needs semver, so frontend/package.json stays 0.1.N
with the same N.

Owner: this script (writes VERSION + frontend/package.json; optional git tag).
Invalidation: pre-commit hook before each new commit; pre-push verifies match;
CI stamps from `git rev-list --count HEAD` with a full clone before packing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = REPO_ROOT / "VERSION"
PACKAGE_JSON = REPO_ROOT / "frontend" / "package.json"
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
TAG_RE = re.compile(r"^v(\d+)$")
PACKAGE_MAJOR = 0
PACKAGE_MINOR = 1
TAG_MIN_WIDTH = 3


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


def target_count_for_hook() -> int:
    count = git_commit_count()
    if is_amend_commit():
        return count
    return count + 1


def format_release_tag(count: int) -> str:
    if count < 1:
        raise ValueError(f"commit count must be >= 1, got {count}")
    return f"v{count:0{TAG_MIN_WIDTH}d}"


def format_package_version(count: int) -> str:
    if count < 1:
        raise ValueError(f"commit count must be >= 1, got {count}")
    return f"{PACKAGE_MAJOR}.{PACKAGE_MINOR}.{count}"


def parse_release_count(text: str) -> int | None:
    raw = text.strip()
    tag = TAG_RE.match(raw)
    if tag:
        return int(tag.group(1))
    semver = SEMVER_RE.match(raw)
    if semver:
        return int(semver.group(3))
    return None


def read_version_file() -> str | None:
    if not VERSION_FILE.is_file():
        return None
    text = VERSION_FILE.read_text(encoding="utf-8").strip()
    return text or None


def write_version_file(tag: str) -> None:
    VERSION_FILE.write_text(f"{tag}\n", encoding="utf-8")


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


def sync_revision(count: int, *, stage: bool = False) -> bool:
    """Write VERSION (vNNN) + package.json (0.1.N). Returns True when changed."""
    tag = format_release_tag(count)
    package = format_package_version(count)
    changed = False
    if read_version_file() != tag:
        write_version_file(tag)
        changed = True
    if read_package_version() != package:
        write_package_version(package)
        changed = True
    if changed and stage:
        subprocess.run(
            ["git", "add", str(VERSION_FILE), str(PACKAGE_JSON)],
            cwd=REPO_ROOT,
            check=True,
        )
    return changed


def expected_tag_for_head() -> str:
    return format_release_tag(git_commit_count())


def expected_package_for_head() -> str:
    return format_package_version(git_commit_count())


def expected_tag_for_next_commit() -> str:
    return format_release_tag(target_count_for_hook())


def run_pre_commit() -> int:
    count = target_count_for_hook()
    tag = format_release_tag(count)
    changed = sync_revision(count, stage=True)
    if changed:
        print(f"bump_version: staged {tag} / {format_package_version(count)}")
    else:
        print(f"bump_version: already {tag}")
    return 0


def run_pre_push() -> int:
    count = git_commit_count()
    expected_tag = format_release_tag(count)
    expected_pkg = format_package_version(count)
    vf = read_version_file()
    pkg = read_package_version()
    problems: list[str] = []
    if vf != expected_tag:
        problems.append(f"VERSION is {vf!r}, expected {expected_tag!r}")
    if pkg != expected_pkg:
        problems.append(f"frontend/package.json is {pkg!r}, expected {expected_pkg!r}")
    if problems:
        print("bump_version: version drift -- run: py -3 tools/bump_version.py --sync")
        for line in problems:
            print(f"  - {line}")
        return 1
    print(f"bump_version: ok ({expected_tag} / {expected_pkg})")
    return 0


def run_sync() -> int:
    count = git_commit_count()
    tag = format_release_tag(count)
    changed = sync_revision(count, stage=False)
    print(f"bump_version: {'updated' if changed else 'already'} {tag}")
    return 0


def run_show() -> int:
    count = git_commit_count()
    print(f"commits={count}")
    print(f"tag={format_release_tag(count)}")
    print(f"package={format_package_version(count)}")
    print(f"next_tag={format_release_tag(target_count_for_hook())}")
    print(f"VERSION_file={read_version_file()}")
    print(f"package_json={read_package_version()}")
    return 0


def run_print_tag() -> int:
    print(format_release_tag(git_commit_count()))
    return 0


def existing_tag_commit(tag: str) -> str | None:
    listed = subprocess.check_output(
        ["git", "tag", "-l", tag],
        cwd=REPO_ROOT,
        text=True,
    ).strip()
    if not listed:
        return None
    return subprocess.check_output(
        ["git", "rev-list", "-n", "1", tag],
        cwd=REPO_ROOT,
        text=True,
    ).strip()


def create_lightweight_tag(tag: str) -> None:
    subprocess.run(["git", "tag", tag], cwd=REPO_ROOT, check=True)


def push_tag(tag: str) -> None:
    subprocess.run(["git", "push", "origin", tag], cwd=REPO_ROOT, check=True)


def run_ensure_tag(*, push: bool = False) -> int:
    """Create vNNN on HEAD when missing. Does not move an existing tag."""
    tag = expected_tag_for_head()
    existing = existing_tag_commit(tag)
    if existing:
        print(f"bump_version: tag {tag} already exists ({existing[:12]})")
        return 0
    create_lightweight_tag(tag)
    print(f"bump_version: created tag {tag}")
    if push:
        push_tag(tag)
        print(f"bump_version: pushed {tag}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nova commit-count vNNN versioning")
    parser.add_argument(
        "--pre-commit",
        action="store_true",
        help="Bump to next commit count and stage version files",
    )
    parser.add_argument(
        "--pre-push",
        action="store_true",
        help="Verify VERSION tag and package.json match current commit count",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Align files to current HEAD commit count (no stage)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Print commit count, vNNN tag, and package semver",
    )
    parser.add_argument(
        "--print-tag",
        action="store_true",
        help="Print only the vNNN tag for HEAD (CI / pack scripts)",
    )
    parser.add_argument(
        "--ensure-tag",
        action="store_true",
        help="Create lightweight git tag vNNN on HEAD if it does not exist",
    )
    parser.add_argument(
        "--push-tag",
        action="store_true",
        help="With --ensure-tag, push the new tag to origin",
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
    if args.print_tag:
        return run_print_tag()
    if args.ensure_tag:
        return run_ensure_tag(push=args.push_tag)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
