"""A reference page's IBKR errors never touch the stock session (ADR 053).

Before this, a 10089 ("requires an additional subscription") on any request set the session's
``live_market_data_blocked`` flag, and the scanner manager then switched the whole connection to delayed
data -- so the Market page asking for ES before the CME subscription reached the Gateway would have moved
the stock desk to delayed quotes.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibkr import reference_errors as ref
from ibkr import session_errors as se

MSG_10089 = "Requested market data requires additional subscription for API. See link in 'Market Data Connections'"


@pytest.fixture(autouse=True)
def _clean():
    se.reset_for_tests()
    ref.reset_for_tests()
    yield
    se.reset_for_tests()
    ref.reset_for_tests()


def _contract(sec_type: str, symbol: str, con_id: int = 0):
    return SimpleNamespace(secType=sec_type, symbol=symbol, conId=con_id)


@pytest.mark.parametrize("sec_type", ["FUT", "CONTFUT", "IND", "CASH", "CRYPTO"])
def test_a_reference_10089_leaves_the_stock_session_live(sec_type):
    se._on_ib_error(41, 10089, MSG_10089, _contract(sec_type, "ES", 495512563))

    assert se.live_market_data_blocked() is False
    assert se.is_delayed_data() is False
    got = ref.last_error(con_id=495512563)
    assert got is not None and got["code"] == 10089 and got["req_id"] == 41
    assert ref.describe(got).startswith("10089: Requested market data")


def test_a_reference_101_does_not_mark_max_tickers():
    se._on_ib_error(42, 101, "Max number of tickers has been reached", _contract("IND", "VIX"))

    assert se.max_tickers_hit() is False
    assert ref.last_error(sec_type="IND", symbol="VIX")["code"] == 101


def test_a_stock_10089_still_sets_the_session_flag():
    se._on_ib_error(43, 10089, MSG_10089, _contract("STK", "AAPL", 265598))

    assert se.live_market_data_blocked() is True
    assert ref.last_error(con_id=265598) is None


def test_an_error_without_a_contract_is_the_sessions():
    se._on_ib_error(-1, 10167, "Displaying delayed market data")

    assert se.is_delayed_data() is True


def test_last_error_since_filters_old_answers():
    ref.note(1, 354, "Requested market data is not subscribed", _contract("FUT", "CL", 7), now=100.0)

    assert ref.last_error(con_id=7, since=99.0)["code"] == 354
    assert ref.last_error(con_id=7, since=101.0) is None
