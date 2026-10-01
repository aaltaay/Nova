"""run_api starts uvicorn without per-message deflate on both paths (#619), at Normal priority."""
from __future__ import annotations

import os

import run_api


def _captured(monkeypatch, reload: str) -> dict:
    import uvicorn

    seen: dict = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: seen.update(kw, app=app))
    monkeypatch.setattr(run_api, "_force_utf8_io", lambda: None)
    monkeypatch.setattr(run_api, "_prepare_sys_path", lambda: None)
    monkeypatch.setattr(run_api, "_normal_priority", lambda: seen.update(priority_raised=True))
    monkeypatch.setenv("NOVA_API_RELOAD", reload)
    cwd = os.getcwd()
    try:
        run_api.main()
    finally:
        os.chdir(cwd)
    return seen


def test_no_deflate_in_process(monkeypatch):
    seen = _captured(monkeypatch, "false")
    assert seen["reload"] is False
    assert seen["ws_per_message_deflate"] is False
    assert seen["priority_raised"] is True


def test_no_deflate_with_reload(monkeypatch):
    seen = _captured(monkeypatch, "true")
    assert seen["app"] == "main:app"
    assert seen["ws_per_message_deflate"] is False
    assert seen["priority_raised"] is True
