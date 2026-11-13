"""Is the phone page on this PC the code on this PC? (ADR 070, operator report 2026-11-13.)

The phone loads a built copy of its page (``frontend/dist``), not the code. On 2026-11-13 two merged
changes were on the PC for hours and the phone still showed the day before: nobody rebuilt, and the
rebuild then failed because two packages the new code needs had never been installed. Both were
invisible until the operator asked why the phone had not changed. This names both, in plain words:

- **Packages:** every package ``frontend/package.json`` asks for is installed, at the version
  ``package-lock.json`` pins. A missing one fails the build.
- **Build:** the built page is newer than every file it is built from. A file changed since (a pull,
  a merge) is not on the phone until the page is built again.

    py -3 tools/phone_page.py check     # read only; exit 0 when the phone has this PC's code, 1 when not
    py -3 tools/phone_page.py update    # side effects: npm install (only when a package is off), then npm run build

``update`` restarts nothing: the file server (``tools/serve_phone_page.py``) hands out the new files
on the phone's next reload.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FRONTEND = REPO / "frontend"
BUILT_PAGE = "dist/phone.html"
# What `npm run build` reads: the code, the pages, the packages and the build's own settings.
SOURCES = ("src", "public", "phone.html", "index.html", "link-test.html", "clip-export.html",
           "package.json", "package-lock.json", "vite.config.ts", "tsconfig.json", "tsconfig.app.json")
# Folders under the sources that the build never reads.
SKIP_DIRS = {"node_modules", "__snapshots__"}


@dataclass
class Report:
    packages: list[str] = field(default_factory=list)
    """One line per package that is missing or at another version than the lock pins."""
    build: str | None = None
    """Why the built page is not this PC's code; None when it is."""
    newest: str | None = None
    """The newest source file, when the build is behind it."""

    @property
    def ok(self) -> bool:
        return not self.packages and self.build is None


def package_problems(frontend: Path) -> list[str]:
    """Each package `package.json` asks for that is not installed at the version the lock pins."""
    manifest = json.loads((frontend / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((frontend / "package-lock.json").read_text(encoding="utf-8")).get("packages", {})
    wanted = {**manifest.get("dependencies", {}), **manifest.get("devDependencies", {})}
    problems: list[str] = []
    for name in sorted(wanted):
        pinned = (lock.get(f"node_modules/{name}") or {}).get("version")
        installed_file = frontend / "node_modules" / name / "package.json"
        if not installed_file.is_file():
            problems.append(f"{name} is not installed" + (f" (the lock pins {pinned})" if pinned else ""))
            continue
        installed = json.loads(installed_file.read_text(encoding="utf-8")).get("version")
        if pinned and installed != pinned:
            problems.append(f"{name} is {installed}; the lock pins {pinned}")
    return problems


def newest_source(frontend: Path) -> tuple[float, Path] | None:
    """The most recently changed file the build reads, by its time on disk (a pull or a checkout sets it)."""
    best: tuple[float, Path] | None = None
    for name in SOURCES:
        root = frontend / name
        files = [root] if root.is_file() else (p for p in root.rglob("*") if p.is_file()) if root.is_dir() else []
        for path in files:
            if SKIP_DIRS.intersection(path.relative_to(frontend).parts):
                continue
            stamp = path.stat().st_mtime
            if best is None or stamp > best[0]:
                best = (stamp, path)
    return best


def check(frontend: Path = FRONTEND) -> Report:
    report = Report(packages=package_problems(frontend))
    built = frontend / BUILT_PAGE
    if not built.is_file():
        report.build = "The phone page has never been built on this PC."
        return report
    newest = newest_source(frontend)
    if newest and newest[0] > built.stat().st_mtime:
        report.build = "The phone page was built before the code it shows last changed."
        report.newest = newest[1].relative_to(frontend).as_posix()
    return report


def describe(report: Report) -> list[str]:
    if report.ok:
        return ["The phone page is this PC's code: every package is installed, and the page is built from the newest code."]
    lines: list[str] = []
    if report.packages:
        lines.append(f"{len(report.packages)} package(s) the code needs are not installed as the lock pins, so a build fails:")
        lines += [f"  - {p}" for p in report.packages]
    if report.build:
        lines.append(report.build + (f" Newest change: {report.newest}." if report.newest else ""))
    lines.append("Fix it: py -3 tools/phone_page.py update   (then reload the page on the phone)")
    return lines


def _npm(frontend: Path, *args: str) -> int:
    # npm is a .cmd on Windows: run it through the shell's lookup, with fixed arguments only.
    return subprocess.call(["npm", "--prefix", str(frontend), *args], shell=sys.platform == "win32")


def update(frontend: Path = FRONTEND) -> int:
    report = check(frontend)
    if report.ok:
        print(describe(report)[0])
        return 0
    if report.packages:
        print("Installing the packages the code needs (npm install)...", flush=True)
        if _npm(frontend, "install") != 0:
            print("npm install failed: the phone page was not rebuilt.", file=sys.stderr)
            return 1
    print("Building the phone page (npm run build)...", flush=True)
    if _npm(frontend, "run", "build") != 0:
        print("The build failed: the phone keeps the page it had.", file=sys.stderr)
        return 1
    after = check(frontend)
    for line in describe(after):
        print(line)
    return 0 if after.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Is the phone page on this PC the code on this PC?")
    parser.add_argument("action", choices=("check", "update"))
    parser.add_argument("--frontend", type=Path, default=FRONTEND)
    args = parser.parse_args(argv)
    if args.action == "update":
        return update(args.frontend)
    report = check(args.frontend)
    for line in describe(report):
        print(line)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
