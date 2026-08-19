"""Classify IBKR managed account ids (mode match)."""
from ibkr.account_kind import (
    accounts_match_mode,
    classify_managed_accounts,
    is_live_account_id,
    is_paper_account_id,
    paper_mode_accounts_ok,
)


def test_paper_prefixes():
    assert is_paper_account_id("DU1234567")
    assert is_paper_account_id("df123")
    assert not is_paper_account_id("U1234567")
    assert not is_paper_account_id("")


def test_live_prefixes():
    assert is_live_account_id("U1234567")
    assert is_live_account_id("F123")
    assert not is_live_account_id("DU123")


def test_classify():
    assert classify_managed_accounts(["DU111"]) == "paper"
    assert classify_managed_accounts(["U111"]) == "live"
    assert classify_managed_accounts(["DU111", "U111"]) == "mixed"
    assert classify_managed_accounts([]) == "unknown"
    assert classify_managed_accounts(["XYZ"]) == "unknown"


def test_accounts_match_mode():
    assert accounts_match_mode("paper", "paper") == (True, "")
    assert accounts_match_mode("live", "live") == (True, "")
    ok, reason = accounts_match_mode("live", "paper")
    assert ok is False
    assert "LIVE" in reason
    ok2, reason2 = accounts_match_mode("paper", "live")
    assert ok2 is False
    assert "PAPER" in reason2
    ok3, _ = accounts_match_mode("mixed", "live")
    assert ok3 is False
    ok4, _ = accounts_match_mode("unknown", "paper")
    assert ok4 is False


def test_paper_mode_accounts_ok():
    assert paper_mode_accounts_ok("paper") == (True, "")
    ok, reason = paper_mode_accounts_ok("live")
    assert ok is False
    assert "LIVE" in reason or "live" in reason.lower()
    ok2, _ = paper_mode_accounts_ok("unknown")
    assert ok2 is False


def test_accept_follows_paper_account_when_nova_asked_live(monkeypatch):
    from ibkr import account_kind as ak
    from ibkr import client as ibkr_client
    from ibkr import gateway_heal as heal

    heal.clear_intentional_mode(reason="test")
    persisted: list[str] = []
    monkeypatch.setattr(
        "ibkr.gateway_heal.persist_gateway_mode",
        lambda mode, env_path=None: persisted.append(mode) or True,
    )
    monkeypatch.setattr("ibkr.gateway_heal.apply_runtime_gateway_mode", lambda mode: None)

    class _Ib:
        def managedAccounts(self):
            return ["DUQ266899"]

    ibkr_client._broker_account_kind = "unknown"
    ok, reason = ak.accept_connected_session(_Ib(), "live")
    assert ok is True
    assert reason == ""
    assert persisted == ["paper"]
    assert ibkr_client._broker_account_kind == "paper"


def test_accept_does_not_follow_paper_during_intentional_live(monkeypatch):
    from ibkr import account_kind as ak
    from ibkr import client as ibkr_client
    from ibkr import gateway_heal as heal

    heal.set_intentional_mode("live")
    persisted: list[str] = []
    monkeypatch.setattr(
        "ibkr.gateway_heal.persist_gateway_mode",
        lambda mode, env_path=None: persisted.append(mode) or True,
    )

    class _Ib:
        def managedAccounts(self):
            return ["DUQ266899"]

    ibkr_client._broker_account_kind = "unknown"
    ok, reason = ak.accept_connected_session(_Ib(), "live")
    assert ok is False
    assert "PAPER" in reason
    assert persisted == []
    heal.clear_intentional_mode(reason="test")


def test_accept_still_refuses_live_account_in_paper_mode():
    from ibkr import account_kind as ak
    from ibkr import client as ibkr_client

    class _Ib:
        def managedAccounts(self):
            return ["U1234567"]

    ibkr_client._broker_account_kind = "unknown"
    ok, reason = ak.accept_connected_session(_Ib(), "paper")
    assert ok is False
    assert "LIVE" in reason


def test_paper_resolve_stays_on_4002_when_only_live_listens(monkeypatch):
    from ibkr import client as ibkr_client

    monkeypatch.setenv("IBKR_ENABLED", "true")
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setenv("IBKR_HOST", "127.0.0.1")
    monkeypatch.setattr(
        "ibkr.port_diagnostics.probe_port",
        lambda _h, p, **_k: p == 4001,
    )
    enabled, host, port, mode, _cid = ibkr_client._resolve_config()
    assert enabled is True
    assert host == "127.0.0.1"
    assert mode == "paper"
    assert port == 4002
