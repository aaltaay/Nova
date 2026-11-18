"""The line a producer writes to hand an event to the phone's notifier: ``tell("practice_fill", row, venue)``.

The producer's line hands over the objects it already holds and reads nothing from them: an argument that
is worked out in the producer's line (``trade.contract.symbol``) runs before this guard and can fail the
producer. Every field is read in ``hooks``, inside the guard.

It imports nothing but the standard library until it is called, and it never raises: whatever goes wrong in
the notifier (a package that will not import, a settings file that will not read) is logged here and the
producer -- an order filling, an alert going out, the loss limit marking -- carries on untouched.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def tell(name: str, *args: Any, **kwargs: Any) -> None:
    """Call ``phone_notify.hooks.<name>`` with the event; a failure is logged, never raised."""
    try:
        from phone_notify import hooks

        getattr(hooks, name)(*args, **kwargs)
    except Exception:
        logger.warning("PHONE NOTIFY: %s could not be handed to the notifier; nothing was sent", name, exc_info=True)
