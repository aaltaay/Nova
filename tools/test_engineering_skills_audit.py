"""Tests for tools/engineering_skills_audit.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "tools" / "engineering_skills_audit.py"


def _load():
    spec = importlib.util.spec_from_file_location("engineering_skills_audit", MODULE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["engineering_skills_audit"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_audit_passes_on_repo():
    mod = _load()
    findings = mod.audit()
    errors = [f for f in findings if f.severity == "error"]
    assert errors == [], errors


def test_main_exit_zero():
    mod = _load()
    assert mod.main([]) == 0


def test_required_skills_listed():
    mod = _load()
    assert "interview-me" in mod.REQUIRED_SKILLS
    assert "verification-before-completion" in mod.REQUIRED_SKILLS
    assert "writing-plans" in mod.REQUIRED_SKILLS
    assert "github-delivery" in mod.REQUIRED_SKILLS
    assert "github-delivery.mdc" in mod.REQUIRED_ALWAYS_ON_MDC
