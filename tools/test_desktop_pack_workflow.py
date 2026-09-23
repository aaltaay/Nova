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


def test_desktop_pack_workflow_gates_prs_and_uploads_the_installer():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request:" in text
    assert "windows-latest" in text
    assert "fetch-depth: 0" in text
    assert "electron:pack" in text
    assert "upload-artifact@v4" in text
    assert "if-no-files-found: error" in text
    assert "Nova-Setup-" in text
    assert "--print-tag" in text
    assert "github.event_name == 'push'" in text
    assert "contents: write" in text
    assert "NOVA_PYTHON" in text
    assert "pull_request.head.sha" in text
    assert "gh release create" in text
    assert "gh release upload" in text
    assert "softprops/action-gh-release" not in text


def test_the_portable_exe_is_gone_from_the_pack():
    """#347: the portable target is retired -- it can never self-update.

    Keeping it would ship a build that cannot take the in-app update this same
    pipeline now feeds, which is the contradiction that decision closed.
    """
    build = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))["build"]
    targets = [
        row["target"] if isinstance(row, dict) else row
        for row in build["win"]["target"]
    ]
    assert targets == ["nsis"]
    assert "portable" not in build
    assert "Nova-Setup-" in build["nsis"]["artifactName"]
    for path in (WORKFLOW, PACK_SCRIPT):
        assert "Nova-Portable-" not in path.read_text(encoding="utf-8")


def test_updater_feed_is_built_verified_and_published():
    """An installed desk reads latest.yml; a Release without it is a dead feed."""
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    assert package["build"]["publish"] == [
        {"provider": "github", "owner": "aaltaay", "repo": "Nova"}
    ]
    # A dependency, not a devDependency: electron-builder packs prod deps only.
    assert package["dependencies"]["electron-updater"].startswith("^6.")
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "latest.yml" in text
    assert ".exe.blockmap" in text
    assert "dist-win/latest.yml" in text


def test_pack_script_builds_the_installer_and_never_publishes():
    text = PACK_SCRIPT.read_text(encoding="utf-8")
    assert "nsis" in text
    assert "'portable'" not in text, "the pack script can still select a portable build"
    assert "--win" in text
    # electron-builder publishes implicitly on a CI tag build otherwise, and
    # the Release must come from the verified artifact, not from the packer.
    assert "'--publish', 'never'" in text


def test_pack_script_stamps_the_revision_as_the_app_version():
    # A hand pack leaves package.json at 0.0.0-dev; without this the installed
    # desk reports 0.0.0-dev in Help and to the update feed.
    text = PACK_SCRIPT.read_text(encoding="utf-8")
    assert "packageVersionFromTag(tag)" in text
    assert "`-c.extraMetadata.version=${version}`" in text


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


def test_npm_electron_pack_uses_the_stamping_script():
    script = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))["scripts"]["electron:pack"]
    assert "run-electron-pack.mjs" in script
    # The target belongs to the script, which also stamps NOVA_RELEASE_TAG.
    assert not script.rstrip().endswith("nsis")


def test_only_a_release_tag_publishes():
    """#347: master merges build and verify; a Release is a deliberate tag.

    A Release is now an update prompt on the operator's desk, so one per merged
    PR -- docs included -- would train dismissal. The pack still runs on master
    (including PR delivery's dispatch after an Actions merge, #346) so a broken
    installer is still caught on the commit that broke it.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text, "pack cannot be dispatched at all"
    assert 'tags: ["v[0-9]+"]' in text, "a pushed release tag does not start the pack"
    assert "startsWith(github.ref, 'refs/tags/v')" in text, (
        "publish-release does not require a release tag"
    )
    assert "github.ref == 'refs/heads/master'" not in text, (
        "a master push still publishes a Release"
    )


def test_a_release_tag_must_match_its_commit_revision():
    """vNNN is the commit count; a tag on another commit would ship a lying feed."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "GITHUB_REF_TYPE" in text and "GITHUB_REF_NAME" in text
    assert 'test "$TAG" = "$REF_TAG"' in text
    assert "--ensure-tag --push-tag" in text, "the workflow does not say how to cut a release"
