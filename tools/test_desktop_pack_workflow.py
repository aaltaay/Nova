"""Contract tests for the Desktop pack CI workflow."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "desktop-pack.yml"


def test_desktop_pack_workflow_exists():
    assert WORKFLOW.is_file(), "missing .github/workflows/desktop-pack.yml"


def test_desktop_pack_workflow_gates_prs_and_uploads_exe():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request:" in text
    assert "windows-latest" in text
    assert "fetch-depth: 0" in text
    assert "electron:pack" in text
    assert "upload-artifact@v4" in text
    assert "if-no-files-found: error" in text
    assert "Nova-Setup-" in text
    assert "--print-tag" in text
    assert "--ensure-tag" in text
    assert "github.event_name == 'push'" in text
    assert "contents: write" in text
    assert "NOVA_PYTHON" in text
    assert "pull_request.head.sha" in text
    assert "gh release" not in text.lower()
    assert "softprops/action-gh-release" not in text
