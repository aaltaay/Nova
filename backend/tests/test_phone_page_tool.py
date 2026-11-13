"""tools/phone_page.py -- is the phone page on this PC the code on this PC? (operator report 2026-11-13)

Two merged phone changes sat on the PC for hours while the phone showed the day before: the page was
never rebuilt, and the rebuild then failed on two packages that had never been installed. These hold
that both are named before anyone has to ask.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools import phone_page  # noqa: E402


def _write(path: Path, text: str, mtime: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.utime(path, (mtime, mtime))


@pytest.fixture
def frontend(tmp_path: Path) -> Path:
    """A frontend with one package pinned and installed, code changed at t=100, page built at t=200."""
    _write(tmp_path / "package.json", json.dumps({"dependencies": {"react": "^19"}, "devDependencies": {"vite": "^8"}}), 100)
    _write(tmp_path / "package-lock.json", json.dumps({"packages": {
        "node_modules/react": {"version": "19.2.0"}, "node_modules/vite": {"version": "8.0.1"},
    }}), 100)
    _write(tmp_path / "node_modules/react/package.json", json.dumps({"version": "19.2.0"}), 50)
    _write(tmp_path / "node_modules/vite/package.json", json.dumps({"version": "8.0.1"}), 50)
    _write(tmp_path / "src/phone/AccountScreen.tsx", "export {}", 100)
    _write(tmp_path / "dist/phone.html", "<html>", 200)
    return tmp_path


def test_a_page_built_after_the_code_with_every_package_is_ok(frontend: Path) -> None:
    report = phone_page.check(frontend)
    assert report.ok
    assert phone_page.main(["check", "--frontend", str(frontend)]) == 0


def test_code_changed_after_the_build_says_the_phone_is_behind_and_which_file(frontend: Path) -> None:
    _write(frontend / "src/phone/screens/AccountCalendar.tsx", "export {}", 300)   # a pull after the build
    report = phone_page.check(frontend)
    assert not report.ok
    assert report.newest == "src/phone/screens/AccountCalendar.tsx"
    assert "built before the code" in report.build


def test_a_package_the_code_needs_but_nobody_installed_is_named(frontend: Path) -> None:
    lock = json.loads((frontend / "package-lock.json").read_text())
    lock["packages"]["node_modules/@fontsource-variable/inter"] = {"version": "5.3.0"}
    _write(frontend / "package-lock.json", json.dumps(lock), 100)
    manifest = json.loads((frontend / "package.json").read_text())
    manifest["dependencies"]["@fontsource-variable/inter"] = "5.3.0"
    _write(frontend / "package.json", json.dumps(manifest), 100)
    report = phone_page.check(frontend)
    assert report.packages == ["@fontsource-variable/inter is not installed (the lock pins 5.3.0)"]
    assert any("not installed" in line for line in phone_page.describe(report))


def test_an_installed_package_at_another_version_than_the_lock_is_named(frontend: Path) -> None:
    _write(frontend / "node_modules/vite/package.json", json.dumps({"version": "7.9.0"}), 50)
    assert phone_page.check(frontend).packages == ["vite is 7.9.0; the lock pins 8.0.1"]


def test_a_page_never_built_is_said(frontend: Path) -> None:
    (frontend / "dist/phone.html").unlink()
    assert phone_page.check(frontend).build == "The phone page has never been built on this PC."


def test_installed_packages_are_not_read_as_code(frontend: Path) -> None:
    # node_modules sits beside src, never under a source folder; a test snapshot never counts either.
    _write(frontend / "src/phone/__snapshots__/x.snap", "", 999)
    assert phone_page.check(frontend).ok


def test_check_sends_nothing_and_update_on_an_ok_page_builds_nothing(frontend: Path, monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(phone_page, "_npm", lambda fe, *args: calls.append(args) or 0)
    assert phone_page.update(frontend) == 0
    assert calls == []


def test_update_installs_only_when_a_package_is_off_then_builds(frontend: Path, monkeypatch) -> None:
    _write(frontend / "src/phone/new.tsx", "export {}", 300)
    calls: list[tuple[str, ...]] = []

    def npm(fe: Path, *args: str) -> int:
        calls.append(args)
        if args == ("run", "build"):
            os.utime(fe / "dist/phone.html", (400, 400))
        return 0

    monkeypatch.setattr(phone_page, "_npm", npm)
    assert phone_page.update(frontend) == 0
    assert calls == [("run", "build")]


def test_a_failed_build_is_said_and_fails(frontend: Path, monkeypatch) -> None:
    _write(frontend / "src/phone/new.tsx", "export {}", 300)
    monkeypatch.setattr(phone_page, "_npm", lambda fe, *args: 1)
    assert phone_page.update(frontend) == 1
