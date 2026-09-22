"""ADR 021 decision 2: the bounded Gateway attach ledger and its use by the dialer."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from constants_diagnostics import (
    IBKR_ATTACH_BACKOFF_SEC,
    IBKR_ATTACH_CAP_REASON,
    IBKR_ATTACH_HUMAN_STEP_POLL_SEC,
    IBKR_ATTACH_MAX_ATTEMPTS_PER_WINDOW,
    IBKR_ATTACH_WINDOW_SEC,
)
from ibkr import attach_retry, session_reconnect

T0 = 1_790_000_000.0


@pytest.fixture(autouse=True)
def _fresh():
    attach_retry.reset_for_tests()
    yield
    attach_retry.reset_for_tests()


def test_backoff_follows_the_schedule_while_nova_can_still_fix_it():
    assert attach_retry.next_delay_sec(now=T0) == IBKR_ATTACH_BACKOFF_SEC[0]
    for i in range(1, IBKR_ATTACH_MAX_ATTEMPTS_PER_WINDOW):
        attach_retry.record_attempt("gateway_authenticating", port=4001, now=T0 + i)
        expected = IBKR_ATTACH_BACKOFF_SEC[min(i, len(IBKR_ATTACH_BACKOFF_SEC)) - 1]
        assert attach_retry.next_delay_sec(now=T0 + i) == expected
    assert attach_retry.human_step() is None


def test_the_window_cap_turns_a_retryable_stall_into_a_human_step():
    for i in range(IBKR_ATTACH_MAX_ATTEMPTS_PER_WINDOW):
        attach_retry.record_attempt("gateway_authenticating", port=4001, now=T0 + i)
    assert attach_retry.human_step() == IBKR_ATTACH_CAP_REASON
    assert attach_retry.next_delay_sec(now=T0 + 10) == IBKR_ATTACH_HUMAN_STEP_POLL_SEC
    status = attach_retry.status(now=T0 + 10)
    assert status["attempts_in_window"] == IBKR_ATTACH_MAX_ATTEMPTS_PER_WINDOW
    assert status["human_step"] == IBKR_ATTACH_CAP_REASON
    assert status["last_attempt"]["reason"] == "gateway_authenticating"


@pytest.mark.parametrize("reason", ["second_factor_pending", "client_id_in_use", "account_kind_mismatch"])
def test_reasons_nova_can_never_fix_are_a_human_step_at_once(reason):
    attach_retry.record_attempt(reason, port=4001, now=T0)
    assert attach_retry.human_step() == reason
    assert attach_retry.next_delay_sec(now=T0) == IBKR_ATTACH_HUMAN_STEP_POLL_SEC


def test_ready_clears_the_episode_and_old_attempts_age_out():
    attach_retry.record_attempt("client_id_in_use", port=4001, now=T0)
    attach_retry.clear(reason="ready", now=T0 + 5)
    status = attach_retry.status(now=T0 + 5)
    assert status["human_step"] is None and status["attempts_in_window"] == 0
    assert status["cleared_reason"] == "ready"
    attach_retry.record_attempt("gateway_authenticating", port=4001, now=T0 + 10)
    later = T0 + 10 + IBKR_ATTACH_WINDOW_SEC + 1
    assert attach_retry.status(now=later)["attempts_in_window"] == 0


def test_the_dialer_never_retries_faster_than_either_schedule(monkeypatch):
    slept: list[float] = []

    async def _sleep(delay: float) -> None:
        slept.append(delay)

    client = SimpleNamespace(_auth_backoff_sec=1.0, _sleep_reconnect=_sleep, set_session_reason=lambda _r: None)
    for _ in range(IBKR_ATTACH_MAX_ATTEMPTS_PER_WINDOW):
        attach_retry.record_attempt("gateway_authenticating", port=4001)
    asyncio.run(session_reconnect.auth_backoff_sleep(client, "127.0.0.1", 4001, "live"))
    # The ledger says "human step, poll every 30 s"; the auth backoff alone would have said 1 s.
    assert slept == [max(1.0, IBKR_ATTACH_HUMAN_STEP_POLL_SEC)]
