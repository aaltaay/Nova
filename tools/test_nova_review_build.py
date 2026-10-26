"""The review page's own build (tools/nova_review_build.py): fresh for the frontend source, rebuilt when it changes.

On 2026-10-24 the checkout's frontend/dist predated the review page, so /review served the desk and every
nova_chart preview failed with REVIEW_SHOT_FAILED. These tests pin the replacement: a build per source
fingerprint, the previous build kept for in-flight pages, a build without the review page refused, a failed
build not retried on every request, and NOVA_REVIEW_DIST left alone.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import nova_review_build as rb  # noqa: E402
import nova_review_engine as engine  # noqa: E402


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
