"""The HOD Momo per-trade debug log (``logs/hod_momo.log``, rotating).

Split out of ``hod_momo_trade.py`` (file-size rule) unchanged: one logger,
its own rotating file, never propagated to the app log.
"""
from __future__ import annotations

import logging
import logging.handlers
import os

from paths import log_dir

trade_log = logging.getLogger("hod_momo.trades")
if not trade_log.handlers:
    _trade_handler = logging.handlers.RotatingFileHandler(
        os.path.join(str(log_dir()), "hod_momo.log"),
        maxBytes=10_000_000,
        backupCount=3,
    )
    _trade_handler.setFormatter(logging.Formatter("%(message)s"))
    trade_log.addHandler(_trade_handler)
    trade_log.setLevel(logging.DEBUG)
    trade_log.propagate = False
