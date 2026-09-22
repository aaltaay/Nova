"""The HOD integrity chip's verdict agrees with the numbers its tooltip prints (QA W27)."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import routes.hod_momo as hod_routes  # noqa: E402
from hod_momo_integrity_common import age_gate  # noqa: E402


def test_a_max_that_prints_as_the_limit_is_not_a_failure():
    chk = age_gate(cid="q", p95=1.0, mx=3.004, p95_limit=2.0, max_limit=3.0, label="active quote age")
    assert chk["status"] != "fail", chk["detail"]
    assert "max=3.00s" in chk["detail"]


def test_a_real_breach_fails_and_prints_limits_as_given():
    chk = age_gate(cid="q", p95=1.0, mx=3.2, p95_limit=2.0, max_limit=0.5, label="eval age")
    assert chk["status"] == "fail"
    # A fractional limit prints as itself, never rounded to "0s".
    assert "max<=0.5s" in chk["detail"]


def test_a_class_share_ticker_reaches_the_inspector_route(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(hod_routes._hod_momo, "get_debug_symbol", lambda sym: seen.append(sym) or {"symbol": sym, "snap": None})
    monkeypatch.setattr(hod_routes._hod_momo, "remove_block", lambda sym: seen.append(f"unblock:{sym}") or [])
    app = FastAPI()
    app.include_router(hod_routes.router)
    client = TestClient(app)

    res = client.get("/api/hod-momo/debug/symbol/BRK%2Fb")
    assert res.status_code == 200
    assert res.json()["symbol"] == "BRK/B"
    assert client.delete("/api/hod-momo/blocklist/BRK%2FB").status_code == 200
    assert seen == ["BRK/B", "unblock:BRK/B"]
