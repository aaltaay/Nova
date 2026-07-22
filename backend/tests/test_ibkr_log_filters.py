"""Tests for ib_async internal-logger noise filtering (Sentry issue reduction).

See PROBLEM_LOG.md / CHANGELOG.md 2026-07-15 and ibkr/log_filters.py for
context — confirmed against live Sentry issues PYTHON-FASTAPI-1/2/3/7/8/9/A.
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ibkr.log_filters import (  # noqa: E402
    BenignIbkrErrorFilter,
    NOISY_IB_ASYNC_LOGGERS,
    install_ibkr_log_filters,
    is_benign_ibkr_log_message,
)


def _make_record(message: str, level: int = logging.ERROR) -> logging.LogRecord:
    return logging.LogRecord(
        name="ib_async.wrapper",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=None,
        exc_info=None,
    )


def test_is_benign_matches_error_162_historical_cancel():
    msg = (
        "Error 162, reqId 1633: Historical Market Data Service error message:"
        "API historical data query cancelled: 1633, contract: Stock(symbol='AEHR')"
    )
    assert is_benign_ibkr_log_message(msg) is True


def test_is_benign_matches_error_365_scanner_subscription():
    msg = "Error 365, reqId 2: No scanner subscription found for ticker id:2"
    assert is_benign_ibkr_log_message(msg) is True


def test_is_benign_matches_cancel_mkt_data_no_reqid():
    msg = (
        "cancelMktData: No reqId found for contract Stock(conId=265598, "
        "symbol='AAPL', exchange='SMART')"
    )
    assert is_benign_ibkr_log_message(msg) is True


def test_is_benign_matches_cancel_mkt_depth_no_reqid():
    msg = "cancelMktDepth: No reqId found for contract Stock(symbol='AAPL')"
    assert is_benign_ibkr_log_message(msg) is True


def test_is_benign_matches_error_300_stale_eid():
    msg = "Error 300, reqId 5948: Can't find EId with tickerId:5948"
    assert is_benign_ibkr_log_message(msg) is True


def test_is_benign_matches_error_10089_market_data_subscription():
    msg = (
        "Error 10089, reqId 36437: Requested market data requires additional "
        "subscription for API. Delayed market data is available.CJMB"
    )
    assert is_benign_ibkr_log_message(msg) is True


def test_is_benign_matches_completed_orders_timeout():
    msg = "completed orders request timed out"
    assert is_benign_ibkr_log_message(msg) is True


def test_is_benign_matches_gateway_port_hint():
    msg = "Make sure API port on TWS/IBG is open"
    assert is_benign_ibkr_log_message(msg) is True


def test_is_benign_false_for_error_101_max_tickers():
    """Capacity oversubscription stays ERROR — real product signal."""
    msg = (
        "Error 101, reqId 7344: Max number of tickers has been reached, "
        "contract: Stock(symbol='MI')"
    )
    assert is_benign_ibkr_log_message(msg) is False


def test_is_benign_false_for_unrelated_error_code():
    msg = "Error 504, reqId 9: Not connected"
    assert is_benign_ibkr_log_message(msg) is False


def test_is_benign_false_for_genuinely_unexpected_message():
    msg = "priceSizeTick: Unknown reqId: 42"
    assert is_benign_ibkr_log_message(msg) is False


def test_filter_downgrades_benign_error_record_to_warning():
    record = _make_record(
        "Error 162, reqId 1: Historical Market Data Service error message:"
        "API historical data query cancelled: 1"
    )
    kept = BenignIbkrErrorFilter().filter(record)
    assert kept is True  # never dropped — still visible in local log files
    assert record.levelno == logging.WARNING
    assert record.levelname == "WARNING"


def test_filter_leaves_unrelated_error_record_at_error_level():
    record = _make_record("tickByTickAllLast: Unknown reqId: 99")
    kept = BenignIbkrErrorFilter().filter(record)
    assert kept is True
    assert record.levelno == logging.ERROR
    assert record.levelname == "ERROR"


def test_install_attaches_filter_once_per_logger():
    for name in NOISY_IB_ASYNC_LOGGERS:
        logging.getLogger(name).filters.clear()

    install_ibkr_log_filters()
    install_ibkr_log_filters()

    for name in NOISY_IB_ASYNC_LOGGERS:
        filters = logging.getLogger(name).filters
        assert sum(isinstance(f, BenignIbkrErrorFilter) for f in filters) == 1


def test_installed_filter_downgrades_via_real_logger_call(caplog):
    for name in NOISY_IB_ASYNC_LOGGERS:
        logging.getLogger(name).filters.clear()
    install_ibkr_log_filters()

    wrapper_logger = logging.getLogger("ib_async.wrapper")
    with caplog.at_level(logging.WARNING, logger="ib_async.wrapper"):
        wrapper_logger.error(
            "Error 365, reqId 5: No historical data query found for ticker id:5"
        )

    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "WARNING"
