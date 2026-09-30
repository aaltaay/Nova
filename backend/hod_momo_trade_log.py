"""The HOD Momo per-trade debug log (``logs/hod_momo.log``, rotating).

Split out of ``hod_momo_trade.py`` (file-size rule): one logger, its own
rotating file, never propagated to the app log.

The caller is the IB loop, once per trade tick (about 14 lines a second on a
busy premarket, 10 MB every 20 minutes). A file write -- and every rotation's
renames -- on that loop stalled it (40 loop stalls on 2026-09-30 sat in its
flush), so the logger only queues the record and one listener thread writes it,
as the app log already does (``logging_setup``).
"""
from __future__ import annotations

import atexit
import logging
import logging.handlers
import os
import queue

from paths import log_dir

trade_log = logging.getLogger("hod_momo.trades")
_listener: logging.handlers.QueueListener | None = None

if not trade_log.handlers:
    _trade_handler = logging.handlers.RotatingFileHandler(
        os.path.join(str(log_dir()), "hod_momo.log"),
        maxBytes=10_000_000,
        backupCount=3,
    )
    _trade_handler.setFormatter(logging.Formatter("%(message)s"))
    _queue: queue.SimpleQueue = queue.SimpleQueue()
    trade_log.addHandler(logging.handlers.QueueHandler(_queue))
    trade_log.setLevel(logging.DEBUG)
    trade_log.propagate = False
    _listener = logging.handlers.QueueListener(_queue, _trade_handler)
    _listener.start()
    atexit.register(_listener.stop)
