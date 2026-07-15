"""Downgrade ib_async's own noisy ERROR-level logs before they reach Sentry.

ib_async's internal loggers (``ib_async.wrapper``, ``ib_async.ib``,
``ib_async.client`` — not our app loggers) log known-benign IBKR conditions
at ERROR: cancelled/no-data historical or scanner queries (Error 162), stale
ticker-id lookups (Error 365), and ``cancelMktData``/``cancelMktDepth`` calls
that lose the race against an already-cleared reqId. Sentry's
LoggingIntegration (see ``observability.py``) opens an issue for every ERROR
record by default, so these spammed the project (confirmed live as
PYTHON-FASTAPI-1/2/3/7/8/9/A).

This filter downgrades matching records to WARNING *in place* — they still
reach local handlers (console + ``backend/logs/blast.log`` via
``logging_setup.py``) at the new level, they just no longer clear Sentry's
ERROR ``event_level`` threshold. Records are never dropped, and anything that
doesn't match a known-benign pattern keeps its original ERROR level and still
reaches Sentry.

Not related to ``ibkr/errors.py``, which classifies *our own* raised
exceptions for the historical-bars code path (a broader, intentionally lax
match used only to decide log level / retry copy for one call site). This
module instead does narrow, precise matching on a third party's log text, so
it does not reuse that classifier's needle list.
"""
from __future__ import annotations

import logging
import re

from constants import IBKR_BENIGN_LOG_ERROR_CODES, IBKR_BENIGN_LOG_MESSAGE_SUBSTRINGS

# Loggers ib_async creates internally — see ib_async/wrapper.py, ib.py, client.py.
NOISY_IB_ASYNC_LOGGERS = ("ib_async.wrapper", "ib_async.ib", "ib_async.client")

_ERROR_CODE_RE = re.compile(r"\berror (\d+),", re.IGNORECASE)


def is_benign_ibkr_log_message(message: str) -> bool:
    """True when an ib_async log line matches a known-benign IBKR pattern."""
    text = message.lower()
    match = _ERROR_CODE_RE.search(text)
    if match and int(match.group(1)) in IBKR_BENIGN_LOG_ERROR_CODES:
        return True
    return any(needle in text for needle in IBKR_BENIGN_LOG_MESSAGE_SUBSTRINGS)


class BenignIbkrErrorFilter(logging.Filter):
    """Downgrades matching ERROR records to WARNING; never drops a record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR and is_benign_ibkr_log_message(record.getMessage()):
            record.levelno = logging.WARNING
            record.levelname = logging.getLevelName(logging.WARNING)
        return True


def install_ibkr_log_filters() -> None:
    """Attach the benign-error filter to ib_async's internal loggers.

    Safe to call even when ib_async is not installed / IBKR is disabled —
    ``logging.getLogger(name)`` just returns/creates a named logger by name;
    ib_async picks up the same (already-filtered) logger object whenever it
    later calls ``logging.getLogger("ib_async.wrapper")`` etc. Idempotent so
    repeated calls (e.g. test imports) don't stack duplicate filters.
    """
    for name in NOISY_IB_ASYNC_LOGGERS:
        target = logging.getLogger(name)
        if not any(isinstance(f, BenignIbkrErrorFilter) for f in target.filters):
            target.addFilter(BenignIbkrErrorFilter())
