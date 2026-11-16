"""The review page's own build (tools/nova_review_build.py): fresh for the frontend source, rebuilt when it changes.

On 2026-10-24 the checkout's frontend/dist predated the review page, so /review served the desk and every
nova_chart preview failed with REVIEW_SHOT_FAILED. These tests pin the replacement: a build per source
fingerprint, the previous build kept for in-flight pages, a build without the review page refused, a failed
build not retried on every request, and NOVA_REVIEW_DIST left alone.

On 2026-11-04 Windows refused the rename of a finished build (WinError 5, a dev server's watcher held assets/),
the exception left ensure_fresh, and /review gave an empty reply. A refused rename now falls back to a copy, and a
build that cannot be put in place is a stale or unavailable status. When master moved, links waited on the whole
build, so requests now get the last good page while the new one builds behind them. The engine has no console, so
every child it starts says no window.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import nova_review_build as rb  # noqa: E402
import nova_review_engine as engine  # noqa: E402
import nova_review_warm as warm  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "frontend" / "src").mkdir(parents=True)
    (root / "frontend" / "src" / "main.tsx").write_text("export const a = 1;\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "one")
    monkeypatch.setattr(rb, "REPO", root)
    monkeypatch.delenv("NOVA_REVIEW_DIST", raising=False)
    monkeypatch.setattr(rb, "_LAST", {"state": "unchecked"})
    monkeypatch.setattr(rb, "_LAST_AT", 0.0)
    monkeypatch.setattr(rb, "_FAILED", ("", 0.0))
    monkeypatch.setattr(rb, "_REBUILD", None)
    return root


def _builder(calls: list, with_review: bool = True, ok: bool = True):
    def build(front: Path, out_dir: Path) -> tuple[bool, str]:
        calls.append(out_dir.name)
        (out_dir / "assets").mkdir(parents=True)
        (out_dir / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
        mark = 'el.setAttribute("data-review-ready","1")' if with_review else "desk()"
        (out_dir / "assets" / "app.js").write_text(mark, encoding="utf-8")
        return ok, "built" if ok else "error TS2304: boom"
    return build


def test_the_fingerprint_follows_committed_and_uncommitted_frontend_source(repo):
    first = rb.source_fingerprint()
    assert first.startswith("git:") and "+" not in first
    (repo / "frontend" / "src" / "main.tsx").write_text("export const a = 2;\n", encoding="utf-8")
    dirty = rb.source_fingerprint()
    assert dirty != first and dirty.startswith(first + "+")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "two")
    assert rb.source_fingerprint() not in (first, dirty)


def test_a_stale_build_is_rebuilt_and_the_previous_one_kept_then_pruned(repo):
    calls: list = []
    first = rb.ensure_fresh(_builder(calls), max_age=0)
    assert first["state"] == "fresh" and len(calls) == 1
    assert rb.ensure_fresh(_builder(calls), max_age=0)["state"] == "fresh" and len(calls) == 1   # unchanged source
    (repo / "frontend" / "src" / "main.tsx").write_text("export const a = 3;\n", encoding="utf-8")
    second = rb.ensure_fresh(_builder(calls), max_age=0)
    assert second["build"] != first["build"] and len(calls) == 2
    current = json.loads((rb.build_root() / "current.json").read_text(encoding="utf-8"))
    assert current["schema_version"] == 1 and current["previous"] == first["build"]
    assert [p.name for p in rb.serving_dirs()] == [second["build"], first["build"]]
    (repo / "frontend" / "src" / "main.tsx").write_text("export const a = 4;\n", encoding="utf-8")
    third = rb.ensure_fresh(_builder(calls), max_age=0)
    kept = sorted(p.name for p in rb.build_root().iterdir() if p.is_dir())
    assert kept == sorted([third["build"], second["build"]])


def test_a_build_without_the_review_page_is_refused_and_a_chart_call_says_so(repo):
    status = rb.ensure_fresh(_builder([], with_review=False), max_age=0)
    assert status["state"] == "unavailable" and status["detail"] == "the build has no review page"
    assert rb.serving_dirs() == []
    missing = engine.page_ready()
    assert missing["error"]["code"] == "REVIEW_BUILD_UNAVAILABLE"


def test_an_old_dist_with_the_review_page_is_the_fallback_when_building_fails(repo):
    dist = repo / "frontend" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("x", encoding="utf-8")
    (dist / "assets" / "r.js").write_text("data-review-ready", encoding="utf-8")
    status = rb.ensure_fresh(_builder([], ok=False), max_age=0)
    assert status["state"] == "stale" and status["source"] == "frontend/dist"
    assert "boom" in status["detail"] and rb.serving_dirs() == [dist]


def test_a_failed_build_is_not_retried_on_every_request(repo):
    calls: list = []
    rb.ensure_fresh(_builder(calls, ok=False), max_age=0)
    rb.ensure_fresh(_builder(calls, ok=False))
    rb.ensure_fresh(_builder(calls, ok=False))
    assert len(calls) == 1


def _refuse_replace(monkeypatch, refused) -> None:
    """os.replace raises WinError 5's PermissionError for the sources `refused` picks, as Windows did."""
    real = os.replace

    def replace(src, dst):
        if refused(Path(src)):
            raise PermissionError(13, "Access is denied", str(src))
        real(src, dst)
    monkeypatch.setattr(rb.os, "replace", replace)


def _leftovers() -> list[str]:
    return [p.name for p in rb.build_root().iterdir() if ".tmp-" in p.name]


def test_a_refused_rename_falls_back_to_a_copy_and_the_build_is_served(repo, monkeypatch):
    _refuse_replace(monkeypatch, Path.is_dir)
    status = rb.ensure_fresh(_builder([]), max_age=0)
    assert status["state"] == "fresh" and status["source"] == "dist-review"
    final = rb.build_root() / status["build"]
    assert rb.has_review_page(final) and rb.serving_dirs() == [final]
    assert rb.read_current()["build"] == status["build"] and _leftovers() == []
    assert engine.page_ready() is None


def test_a_build_that_cannot_be_put_in_place_is_unavailable_not_an_exception(repo, monkeypatch):
    def half_a_copy(src, dst, **_kwargs):
        (Path(dst) / "assets").mkdir(parents=True)
        (Path(dst) / "index.html").write_text("x", encoding="utf-8")
        raise shutil.Error([(str(src), str(dst), "Access is denied")])

    _refuse_replace(monkeypatch, Path.is_dir)
    monkeypatch.setattr(rb.shutil, "copytree", half_a_copy)
    calls: list = []
    status = rb.ensure_fresh(_builder(calls), max_age=0)
    assert status["state"] == "unavailable" and status["source"] == "none"
    assert status["detail"].startswith("the build could not be put in place")
    assert sorted(p.name for p in rb.build_root().iterdir()) == ["build.log"]        # no tmp, no half a build
    assert engine.page_ready()["error"]["code"] == "REVIEW_BUILD_UNAVAILABLE"
    rb.ensure_fresh(_builder(calls))
    assert len(calls) == 1                                                           # not rebuilt per request


def test_the_last_build_stays_served_when_the_next_cannot_be_put_in_place(repo, monkeypatch):
    first = rb.ensure_fresh(_builder([]), max_age=0)
    (repo / "frontend" / "src" / "main.tsx").write_text("export const a = 5;\n", encoding="utf-8")
    _refuse_replace(monkeypatch, lambda src: True)                                   # current.json refused as well
    status = rb.ensure_fresh(_builder([]), max_age=0)
    assert status["state"] == "stale" and status["source"] == "dist-review" and status["build"] == first["build"]
    assert rb.serving_dirs()[0].name == first["build"] and rb.read_current()["build"] == first["build"]
    assert _leftovers() == []


def test_a_request_gets_the_last_good_page_while_the_new_one_builds_behind_it(repo, monkeypatch):
    first = rb.ensure_fresh(_builder([]), max_age=0)
    (repo / "frontend" / "src" / "main.tsx").write_text("export const a = 6;\n", encoding="utf-8")
    started, release = threading.Event(), threading.Event()
    build = _builder([])

    def slow_build(front: Path, out_dir: Path) -> tuple[bool, str]:
        started.set()
        assert release.wait(10)
        return build(front, out_dir)

    monkeypatch.setattr(rb, "vite_build", slow_build)
    monkeypatch.setattr(rb, "CHECK_EVERY_SEC", 0)
    assert engine.page_ready() is None and started.wait(5)
    assert engine.page_ready() is None                                               # the build is still running
    assert rb.serving_dirs()[0].name == first["build"]
    assert rb.last_status()["state"] == "stale" and rb.last_status()["detail"] == "a new build is running"
    thread = rb._REBUILD
    release.set()
    thread.join(10)
    assert rb.last_status()["state"] == "fresh" and rb.serving_dirs()[0].name != first["build"]


def test_a_request_with_nothing_to_serve_waits_for_the_build(repo, monkeypatch):
    monkeypatch.setattr(rb, "vite_build", _builder([]))
    assert engine.page_ready() is None and rb.last_status()["state"] == "fresh"


def test_no_child_of_the_engine_opens_a_console_window(repo, monkeypatch):
    seen: list = []

    def run(cmd, **kwargs):
        seen.append((cmd[0], kwargs.get("creationflags")))
        raise OSError("not started")

    monkeypatch.setattr(rb.subprocess, "run", run)
    monkeypatch.setattr(rb.subprocess, "Popen", run)
    monkeypatch.setattr(rb.shutil, "which", lambda _name: "node")
    (repo / "frontend" / "node_modules" / "vite" / "bin").mkdir(parents=True)
    (repo / "frontend" / "node_modules" / "vite" / "bin" / "vite.js").write_text("", encoding="utf-8")
    assert rb._git("status") is None
    assert rb.vite_build(rb.frontend_dir(), rb.build_root() / "x")[0] is False
    assert warm.ReviewShots().start()["ok"] is False
    assert seen == [("git", rb.NO_WINDOW), ("node", rb.NO_WINDOW), ("node", warm.NO_WINDOW)]


def test_the_dev_server_does_not_watch_the_review_builds():
    config = Path(__file__).resolve().parents[1] / "frontend" / "vite.config.ts"
    assert "'**/dist-review/**'" in config.read_text(encoding="utf-8")


def test_an_unknown_schema_version_is_rebuilt_not_served(repo):
    root = rb.build_root()
    (root / "old" / "assets").mkdir(parents=True)
    (root / "current.json").write_text(json.dumps({"schema_version": 99, "build": "old"}), encoding="utf-8")
    assert rb.read_current() is None and rb.serving_dirs() == []
    calls: list = []
    assert rb.ensure_fresh(_builder(calls), max_age=0)["state"] == "fresh" and len(calls) == 1


def test_nova_review_dist_is_served_as_given_and_never_built(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_REVIEW_DIST", str(tmp_path / "given"))
    calls: list = []
    assert rb.ensure_fresh(_builder(calls))["state"] == "override" and calls == []
    assert rb.serving_dirs() == [tmp_path / "given"]
