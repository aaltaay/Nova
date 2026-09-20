"""Contract tests for the Desktop pack CI workflow."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "desktop-pack.yml"
PACKAGE_JSON = REPO_ROOT / "frontend" / "package.json"
PACK_SCRIPT = REPO_ROOT / "frontend" / "scripts" / "run-electron-pack.mjs"
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
TS_MODULE_SUFFIXES = {".ts", ".tsx", ".mts", ".cts", ".js", ".jsx"}


def windows_module_stem_collisions(paths: list[str]) -> dict[str, list[str]]:
    """Group same-folder TS/JS files whose stems collide on Windows.

    `import './MwcbBanner'` and `import './mwcbBanner'` resolve to one
    Windows path even when the extensions differ (`.tsx` vs `.ts`).
    CSS siblings (`AdvisePanel.tsx` + `advisePanel.css`) are a known
    pattern and are ignored -- those imports keep the `.css` suffix.
    """
    groups: dict[str, list[str]] = defaultdict(list)
    for path in paths:
        parsed = Path(path)
        if parsed.suffix.lower() not in TS_MODULE_SUFFIXES:
            continue
        parent = str(parsed.parent).replace("\\", "/").casefold()
        groups[f"{parent}/{parsed.stem.casefold()}"].append(path)
    return {key: names for key, names in groups.items() if len(names) > 1}


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


def test_windows_case_collisions_detects_mwcb_banner_pair():
    hits = windows_module_stem_collisions(
        [
            "ibkr/MwcbBanner.tsx",
            "ibkr/mwcbBanner.ts",
            "ibkr/MwcbBanner.test.tsx",
            "ibkr/mwcbBanner.test.ts",
            "ibkr/mwcbDesk.ts",
            "ibkr/MwcbBanner.css",
            "ibkr/mwcbBanner.css",
        ]
    )
    assert sorted(hits["ibkr/mwcbbanner"]) == [
        "ibkr/MwcbBanner.tsx",
        "ibkr/mwcbBanner.ts",
    ]
    assert sorted(hits["ibkr/mwcbbanner.test"]) == [
        "ibkr/MwcbBanner.test.tsx",
        "ibkr/mwcbBanner.test.ts",
    ]
    assert "ibkr/mwcbdesk" not in hits


def test_frontend_src_has_no_windows_case_collisions():
    rels = [
        str(path.relative_to(FRONTEND_SRC)).replace("\\", "/")
        for path in FRONTEND_SRC.rglob("*")
        if path.is_file()
    ]
    hits = windows_module_stem_collisions(rels)
    assert hits == {}, f"Windows Desktop pack cannot distinguish: {hits}"


def test_npm_electron_pack_does_not_force_nsis_only():
    script = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))["scripts"]["electron:pack"]
    assert "run-electron-pack.mjs" in script
    assert not script.rstrip().endswith("nsis")
    assert "portable" in json.dumps(
        json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))["build"]["win"]["target"]
    )


def test_publish_accepts_an_actions_merge_dispatch():
    """A dispatched master run must publish, not just a pushed one.

    `tools/pr_delivery.py` merges with `GITHUB_TOKEN`, which by design starts
    no `push:` run. Gating publish on `push` alone is what left master at
    v757 with no tag, Release or EXE (#346).
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text, "pack cannot be dispatched at all"
    assert "github.event_name == 'workflow_dispatch'" in text, (
        "publish-release still gates on push only -- an Actions merge "
        "would publish nothing"
    )
    # A dispatch of any other ref must still not publish.
    assert "github.ref == 'refs/heads/master'" in text
