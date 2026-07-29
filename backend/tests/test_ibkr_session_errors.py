"""Session-level IBKR errorEvent handler (G4 capture-audit remediation)."""
from __future__ import annotations

from ibkr import session_errors as se
from ibkr import session_state as session_state
from ibkr import scanner_l1


class _FakeErrorEvent:
    def __init__(self) -> None:
        self.handlers: list = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def fire(self, *args) -> None:
        for handler in list(self.handlers):
            handler(*args)


class _FakeIB:
    def __init__(self) -> None:
        self.errorEvent = _FakeErrorEvent()


def setup_function() -> None:
    se.reset_for_tests()
    session_state.set_ready()
    scanner_l1._subscription_state["error"] = None


def test_install_is_idempotent_per_ib_instance():
    ib = _FakeIB()
    se.install_error_hook(ib)
    se.install_error_hook(ib)
    assert len(ib.errorEvent.handlers) == 1


def test_connectivity_lost_sets_degraded():
    ib = _FakeIB()
    se.install_error_hook(ib)
    session_state.set_ready()
    ib.errorEvent.fire(1, 1100, "Connectivity between IB and TWS has been lost.", None)
    assert session_state.state() == session_state.DEGRADED


def test_data_farm_notice_recorded():
    ib = _FakeIB()
    se.install_error_hook(ib)
    ib.errorEvent.fire(1, 2104, "Market data farm connection is OK:usfarm", None)
    status = se.get_data_farm_status()
    assert status["status"] is not None
    assert "usfarm" in status["status"]
    assert status["ts"]


def test_max_tickers_sets_scanner_l1_error():
    ib = _FakeIB()
    se.install_error_hook(ib)
    ib.errorEvent.fire(1, 101, "Max number of tickers has been reached", None)
    assert se.max_tickers_hit() is True
    err = scanner_l1.get_subscription_state().get("error") or ""
    assert "101" in err or "max tickers" in err.lower()


def test_delayed_data_notice_sets_flag():
    ib = _FakeIB()
    se.install_error_hook(ib)
    assert se.is_delayed_data() is False
    ib.errorEvent.fire(
        1, 10167,
        "Requested market data is not subscribed. Displaying delayed market data.",
        None,
    )
    assert se.is_delayed_data() is True


def test_unrelated_error_codes_are_ignored():
    ib = _FakeIB()
    se.install_error_hook(ib)
    ib.errorEvent.fire(1, 200, "No security definition found", None)
    assert se.is_delayed_data() is False
    assert se.max_tickers_hit() is False
    assert se.get_data_farm_status()["status"] is None
