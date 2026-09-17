"""nova-brain llm-decide -- mock HTTP; fire only when L2+Activate."""
from __future__ import annotations

import json

from constants_bot import BOT_LEVEL_EYES, BOT_PACK_LLM_DECIDE
from nova_brain.llm_decide import parse_proposals, tick


def _session(**extra):
    row = {
        "level": BOT_LEVEL_EYES,
        "armed": False,
        "active_pack": BOT_PACK_LLM_DECIDE,
        "live_fire_ready": False,
        "caps": {"max_shares": 1, "allowlist": ["buy_market"]},
        "llm": {
            "configured": True,
            "live_fire": False,
            "call_cap": 10,
            "usd_cap": 2.0,
            "usd_spent": 0.0,
            "calls_used": 0,
        },
        "symbol_allowlist": ["ABCD"],
        "trader_live": ["ABCD"],
    }
    row.update(extra)
    return row


def _llm_action():
    return {
        "content": json.dumps(
            {
                "proposals": [
                    {
                        "symbol": "ABCD",
                        "side": "BUY",
                        "kind": "buy_market",
                        "reason": "halt clear tape",
                        "confidence": 0.7,
                    }
                ]
            }
        ),
        "usage": {"prompt_tokens": 10, "completion_tokens": 8},
    }


def test_parse_refuses_off_allowlist_qty_and_junk():
    eligible = {"ABCD"}
    kinds = {"buy_market"}
    assert parse_proposals("not-json", eligible, kinds) == []
    assert parse_proposals(json.dumps({"proposals": []}), eligible, kinds) == []
    bad = {
        "proposals": [
            {"symbol": "ZZZZ", "side": "BUY", "kind": "buy_market", "reason": "x"},
            {"symbol": "ABCD", "side": "BUY", "kind": "buy_market", "reason": "ok", "qty": 9},
            {"symbol": "ABCD", "side": "HOLD", "kind": "buy_market", "reason": "x"},
            {"symbol": "ABCD", "side": "BUY", "kind": "buy_market", "reason": "gap hold"},
        ]
    }
    got = parse_proposals(json.dumps(bad), eligible, kinds)
    assert got == [
        {
            "symbol": "ABCD",
            "side": "BUY",
            "kind": "buy_market",
            "reason": "gap hold",
            "confidence": None,
        }
    ]


class _FakeClient:
    def __init__(self, session: dict | None = None) -> None:
        self._session = session or _session()
        self.proposed: list[dict] = []
        self.fired: list[tuple[str, str]] = []
        self.charges: list[float] = []
        self.claims = 0
        self.heartbeats = 0

    def session_get(self) -> dict:
        return dict(self._session)

    def claim(self) -> dict:
        self.claims += 1
        return dict(self._session)

    def heartbeat(self) -> dict:
        self.heartbeats += 1
        return dict(self._session)

    def watch(self) -> dict:
        return {
            "symbols": [
                {
                    "symbol": "ABCD",
                    "halted": False,
                    "last": 1.25,
                    "position_qty": 0,
                }
            ],
            "eligible": ["ABCD"],
        }

    def propose(self, body: dict) -> dict:
        self.proposed.append(body)
        return {"ok": True, **body}

    def charge_llm(self, usd: float) -> dict:
        self.charges.append(usd)
        return {"ok": True}

    def fire(self, kind: str, symbol: str) -> dict:
        self.fired.append((kind, symbol))
        return {"ok": True}


def test_tick_idle_without_key(monkeypatch):
    monkeypatch.delenv("NOVA_LLM_API_KEY", raising=False)
    monkeypatch.delenv("NOVA_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("NOVA_LLM_MODEL", raising=False)
    client = _FakeClient()
    calls = {"n": 0}

    def boom(*_a, **_k):
        calls["n"] += 1
        raise AssertionError("LLM HTTP must not run without a key")

    monkeypatch.setattr("nova_brain.llm_http.chat", boom)
    tick(
        client,
        session=_session(
            llm={
                "configured": False,
                "call_cap": 10,
                "usd_cap": 2,
                "usd_spent": 0,
                "calls_used": 0,
            }
        ),
        now=100.0,
        last={"ts": 0.0},
    )
    assert calls["n"] == 0
    assert client.proposed == []
    assert client.fired == []


def test_tick_proposes_when_activate_off(monkeypatch):
    monkeypatch.setenv("NOVA_LLM_API_KEY", "test-key")
    monkeypatch.setenv("NOVA_LLM_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("NOVA_LLM_MODEL", "test-model")
    monkeypatch.setattr("nova_brain.llm_http.chat", lambda *_a, **_k: _llm_action())
    client = _FakeClient()
    tick(client, session=_session(), now=100.0, last={"ts": 0.0})
    assert client.fired == []
    assert len(client.proposed) == 1
    assert client.proposed[0]["symbol"] == "ABCD"
    assert "qty" not in client.proposed[0]
    assert client.charges


def test_tick_fires_when_l2_activate_eligible(monkeypatch):
    monkeypatch.setenv("NOVA_LLM_API_KEY", "test-key")
    monkeypatch.setenv("NOVA_LLM_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("NOVA_LLM_MODEL", "test-model")
    monkeypatch.setattr("nova_brain.llm_http.chat", lambda *_a, **_k: _llm_action())
    session = _session(level=2, armed=True, live_fire_ready=True, llm={**_session()["llm"], "live_fire": True})
    client = _FakeClient(session)
    tick(client, session=session, now=100.0, last={"ts": 0.0})
    assert client.fired == [("buy_market", "ABCD")]
    assert client.proposed == []
    assert client.charges


def test_step_llm_pack_at_l1_proposes_without_claim(monkeypatch):
    from nova_brain.loop import step

    monkeypatch.setenv("NOVA_LLM_API_KEY", "test-key")
    monkeypatch.setenv("NOVA_LLM_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("NOVA_LLM_MODEL", "test-model")
    monkeypatch.setattr("nova_brain.llm_http.chat", lambda *_a, **_k: _llm_action())
    client = _FakeClient()
    step(client, halt_prev={}, last_fire={}, last_llm={"ts": 0.0})
    assert client.claims == 0
    assert client.heartbeats == 0
    assert client.fired == []
    assert client.proposed[0]["symbol"] == "ABCD"


def test_step_llm_pack_fires_only_when_l2_activate(monkeypatch):
    from nova_brain.loop import step

    monkeypatch.setenv("NOVA_LLM_API_KEY", "test-key")
    monkeypatch.setenv("NOVA_LLM_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("NOVA_LLM_MODEL", "test-model")
    monkeypatch.setattr("nova_brain.llm_http.chat", lambda *_a, **_k: _llm_action())

    live = _session(level=2, armed=True, live_fire_ready=True)
    client = _FakeClient(live)
    step(client, halt_prev={}, last_fire={}, last_llm={"ts": 0.0})
    assert client.claims == 1
    assert client.heartbeats == 1
    assert client.fired == [("buy_market", "ABCD")]
    assert client.proposed == []

    off = _session(level=2, armed=False, live_fire_ready=False)
    idle = _FakeClient(off)
    step(idle, halt_prev={}, last_fire={}, last_llm={"ts": 0.0})
    assert idle.claims == 0
    assert idle.fired == []
    assert idle.proposed[0]["kind"] == "buy_market"
