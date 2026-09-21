"""Exercise skipped coverage boundaries and complete git diffs, including renames."""

import subprocess

import pytest

from tools.ci_scope import FIELDS, changed_paths, classify, full_scope, select_scope


@pytest.mark.parametrize("paths", [
    ["README.md"], ["docs/ci.md"],
    ["knowledge/task-log/2026-09-20-ci.md"],
])
def test_non_application_changes_skip_heavy_checks(paths):
    scope = classify(paths)
    assert not any(scope[field] for field in ("backend", "frontend", "e2e", "desktop"))


def test_backend_retains_complete_suite_e2e_and_pack():
    assert classify(["backend/execution/service.py"]) == dict(
        backend=True, frontend=False, e2e=True, desktop=True, source=True, dependencies=False,
    )


def test_frontend_visual_changes_do_not_run_backend():
    assert classify(["frontend/src/styles/table.css"]) == dict(
        backend=False, frontend=True, e2e=True, desktop=True, source=True, dependencies=False,
    )


@pytest.mark.parametrize("path", [
    "frontend/src/ibkr/ManualOrderTicket.tsx", "frontend/src/hotkeys/useOrders.ts",
    "frontend/src/bot/session.ts", "frontend/src/sim/orders.ts",
    "frontend/src/api/novaFetch.ts", "frontend/src/constantGroups/ibkr.ts",
])
def test_trading_frontend_also_runs_backend_safeguards(path):
    scope = classify([path])
    assert all(scope[field] for field in ("backend", "frontend", "e2e", "desktop"))


@pytest.mark.parametrize("path", [
    "frontend/electron/main.mjs", "frontend/scripts/build-api-sidecar.mjs",
    "frontend/package-lock.json", "backend/requirements.txt", "pyproject.toml",
    ".github/workflows/deploy.yml", "tools/ci_scope.py", "new-runtime/foo.py",
    "docs/generate.py", "frontend/vite.config.ts", ".env.example",
])
def test_shared_or_unknown_paths_select_full_verification(path):
    assert classify([path]) == full_scope()


def test_mixed_docs_and_source_is_union():
    scope = classify(["docs/ci.md", "frontend/src/styles/table.css", "backend/cache.py"])
    assert all(scope[field] for field in FIELDS if field != "dependencies")


def test_empty_manual_and_missing_diff_select_everything(tmp_path):
    assert classify([]) == full_scope()
    assert select_scope("workflow_dispatch", {}, tmp_path) == full_scope()
    assert select_scope("pull_request", {}, tmp_path) == full_scope()
    assert select_scope("push", {"before": "0" * 40, "after": "1" * 40}, tmp_path) == full_scope()


def test_rename_from_runtime_to_docs_cannot_hide_deleted_source(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    git("init")
    git("config", "user.name", "CI test")
    git("config", "user.email", "ci@example.invalid")
    (tmp_path / "backend").mkdir()
    source = tmp_path / "backend" / "module.py"
    source.write_text("print('fixture')\n", encoding="utf-8")
    git("add", "backend/module.py")
    git("commit", "-m", "base")
    base = git("rev-parse", "HEAD")
    source.rename(tmp_path / "README.md")
    git("add", "backend/module.py", "README.md")
    git("commit", "-m", "rename")
    head = git("rev-parse", "HEAD")
    event = {"pull_request": {"base": {"sha": base}, "head": {"sha": head}}}
    paths = changed_paths("pull_request", event, tmp_path)
    assert set(paths) == {"backend/module.py", "README.md"}
    assert select_scope("pull_request", event, tmp_path)["backend"] is True
    assert changed_paths("push", {"before": base, "after": head}, tmp_path) == paths


def test_diff_endpoints_cannot_be_git_options(tmp_path):
    assert select_scope("push", {"before": "--output=bad", "after": "HEAD"}, tmp_path) == full_scope()
