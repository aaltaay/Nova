"""Drop epoch-0 / 1969-12-31 L1 archive rows and their cold folder."""
from __future__ import annotations

import logging
import shutil

from pathlib import Path

from archive import db as archive_db
from constants import ARCHIVE_COLD_DIRNAME

logger = logging.getLogger(__name__)

_BAD_SESSION = "1969-12-31"


def purge_epoch_zero_l1() -> int:
    """Delete L1 ticks dated before 2000 (the 1969-12-31 partition epoch-0 rows land in).

    It runs on every backend start, so it reads ``idx_l1_ticks_date`` only. It used to add
    ``ts <= 0``, which no index serves: SQLite scanned the whole ``l1_ticks`` table of a
    2.8 GB archive, about 28 s of every restart (2026-09-30). Both L1 writers
    (``archive.capture.record_l1_tick``, ``archive.write_queue.enqueue_l1_tick``) refuse
    ``ts <= 0``, and such a row is dated by its ts, so the date alone finds it.
    """
    deleted = 0
    conn = archive_db.get_connection()
    try:
        cur = conn.execute("DELETE FROM l1_ticks WHERE session_date < '2000-01-01'")
        deleted = int(cur.rowcount or 0)
        conn.commit()
    finally:
        conn.close()
    cold = Path(archive_db.cache_dir()) / ARCHIVE_COLD_DIRNAME / _BAD_SESSION
    if cold.is_dir():
        shutil.rmtree(cold, ignore_errors=True)
    if deleted:
        logger.warning("archive.l1_cleanup: removed %s epoch-0 L1 rows", deleted)
    return deleted
