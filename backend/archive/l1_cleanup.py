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
    """Delete L1 ticks with ts<=0 or the 1969-12-31 session partition."""
    deleted = 0
    conn = archive_db.get_connection()
    try:
        cur = conn.execute(
            """
            DELETE FROM l1_ticks
            WHERE ts <= 0 OR session_date = ? OR session_date < '2000-01-01'
            """,
            (_BAD_SESSION,),
        )
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
