"""Session-level IBKR errorEvent handler (G4 + usable-session SoT)."""
from __future__ import annotations

from unittest.mock import patch

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
    session_state.reset_for_testing()
    session_state.set_ready()
    scanner_l1._subscription_state["error"] = None


def test_install_is_idempotent_per_ib_instance():
    ib = _FakeIB()
    se.install_error_hook(ib)
    se.install_error_hook(ib)
    assert len(ib.errorEvent.handlers) == 1


def test_connectivity_lost_sets_degraded_and_stamps_unusable():
    ib = _FakeIB()
    se.install_error_hook(ib)
    session_state.set_ready()
    with patch("ibkr.client.wake_reconnect_loop") as wake, \
         patch("ibkr.client.set_session_reason") as reason:
        ib.errorEvent.fire(1, 1100, "Connectivity between IB and TWS has been lost.", None)
        wake.assert_called_once()
        reason.assert_called_with("connectivity_lost")
    assert session_state.state() == session_state.DEGRADED
    assert se.unusable_since() is not None
    assert se.last_connectivity_code() == 1100
    assert se.peek_restore_pending() is None


def test_connectivity_restored_data_lost_enqueues_restore_and_wakes():
    ib = _FakeIB()
    se.install_error_hook(ib)
    session_state.set_degraded()
    se.stamp_unusable(code=1100)
    with patch("ibkr.client.wake_reconnect_loop") as wake, \
         patch("ibkr.client.set_session_reason") as reason:
        ib.errorEvent.fire(
            1, 1101,
            "Connectivity between IB and TWS has been restored- data lost.",
            None,
        )
        wake.assert_called_once()
        reason.assert_called_with("connectivity_data_lost")
    assert se.peek_restore_pending() == "data_lost"
    assert se.take_restore_pending() == "data_lost"
    assert se.peek_restore_pending() is None
    assert se.last_connectivity_code() == 1101


def test_connectivity_restored_data_kept_enqueues_restore_and_wakes():
    ib = _FakeIB()
    se.install_error_hook(ib)
    with patch("ibkr.client.wake_reconnect_loop") as wake, \
         patch("ibkr.client.set_session_reason") as reason:
        ib.errorEvent.fire(
            1, 1102,
            "Connectivity between IB and TWS has been restored- data maintained.",
            None,
        )
        wake.assert_called_once()
        reason.assert_called_with("connectivity_restored")
    assert se.peek_restore_pending() == "data_kept"
    assert se.last_connectivity_code() == 1102


def test_reset_for_tests_clears_connectivity_stamps():
    se.stamp_unusable(code=1100)
    se._restore_pending = "data_kept"  # type: ignore[attr-defined]
    se.reset_for_tests()
    assert se.unusable_since() is None
    assert se.last_connectivity_code() is None
    assert se.peek_restore_pending() is None


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


def test_md_requires_subscription_blocks_live_and_marks_delayed():
    """Error 10089 — paper without shared live MD (2026-08-07)."""
    ib = _FakeIB()
    se.install_error_hook(ib)
    assert se.live_market_data_blocked() is False
    ib.errorEvent.fire(
        14, 10089,
        "Requested market data requires additional subscription for API. "
        "Delayed market data is available.",
        None,
    )
    assert se.live_market_data_blocked() is True
    assert se.is_delayed_data() is True


def test_client_id_in_use_sets_reason_and_code():
    ib = _FakeIB()
    se.install_error_hook(ib)
    with patch("ibkr.client.set_session_reason") as reason:
        ib.errorEvent.fire(
            -1, 326,
            "Unable to connect as the client id is already in use.",
            None,
        )
        reason.assert_called_with("client_id_in_use")
    assert se.last_connectivity_code() == 326
    assert se.unusable_since() is not None


def test_unrelated_error_codes_are_ignored():
    ib = _FakeIB()
    se.install_error_hook(ib)
    ib.errorEvent.fire(1, 200, "No security rules definition found", None)
    assert se.is_delayed_data() is False
    assert se.live_market_data_blocked() is False
    assert se.max_tickers_hit() is False
    assert se.get_data_farm_status()["status"] is None
    assert se.peek_restore_pending() is None
