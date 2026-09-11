"""Contract tests for the Desktop pack CI workflow."""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "desktop-pack.yml"
PACKAGE_JSON = REPO_ROOT / "frontend" / "package.json"
PACK_SCRIPT = REPO_ROOT / "frontend" / "scripts" / "run-electron-pack.mjs"


def test_desktop_pack_workflow_exists():
    assert WORKFLOW.is_file(), "missing .github/workflows/desktop-pack.yml"


def test_desktop_pack_workflow_gates_prs_and_uploads_exes():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request:" in text
    assert "windows-latest" in text
    assert "fetch-depth: 0" in text
    assert "electron:pack" in text
    assert "upload-artifact@v4" in text
    assert "if-no-files-found: error" in text
    assert "Nova-Setup-" in text
    assert "Nova-Portable-" in text
    assert "--print-tag" in text
    assert "--ensure-tag" in text
    assert "github.event_name == 'push'" in text
    assert "contents: write" in text
    assert "NOVA_PYTHON" in text
    assert "pull_request.head.sha" in text
    assert "gh release create" in text
    assert "gh release upload" in text
    assert "softprops/action-gh-release" not in text


def test_electron_builder_names_setup_and_portable():
    build = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))["build"]
    targets = [
        row["target"] if isinstance(row, dict) else row
        for row in build["win"]["target"]
    ]
    assert "nsis" in targets
    assert "portable" in targets
    setup_name = build["nsis"]["artifactName"]
    portable_name = build["portable"]["artifactName"]
    assert "Nova-Setup-" in setup_name
    assert "Nova-Portable-" in portable_name
    assert setup_name != portable_name


def test_pack_script_defaults_to_nsis_and_portable():
    text = PACK_SCRIPT.read_text(encoding="utf-8")
    assert "nsis" in text
    assert "portable" in text
    assert "--win" in text
