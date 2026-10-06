"""One Massive import, run out of the API process (ADR 046).

    python -m sim.massive_worker --job-id ID
    nova-api.exe --massive-import --job-id ID      (the frozen desk)

An import inflates gigabytes and parses a ticker's rows for seconds to minutes. In
the API process that work would share the GIL with the event loops that carry the
desk's Level 2, tape and orders (ADR 045), so it runs here, below normal priority,
and talks to the API only through the Massive store: the job's progress and its end.
The API pauses an import by ending this process; nothing is written before the
window's final transaction, so an ended import leaves no partial window.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys


def _lower_priority() -> None:
    try:
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.kernel32.SetPriorityClass(ctypes.c_void_p(-1), 0x00004000)   # BELOW_NORMAL_PRIORITY_CLASS
        else:
            os.nice(10)
    except Exception:
        logging.getLogger(__name__).warning("massive import: could not lower its priority", exc_info=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="massive-import")
    parser.add_argument("--massive-import", action="store_true")
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args(argv)
    _lower_priority()
    try:
        from paths import log_dir

        logging.basicConfig(filename=str(log_dir() / "massive_import.log"), level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    except Exception:
        logging.basicConfig(level=logging.INFO)
    from sim import massive_import, massive_store

    log = logging.getLogger("sim.massive_worker")
    log.info("import %s starts (pid %s)", args.job_id, os.getpid())
    try:
        massive_import.run(args.job_id)
    except Exception as exc:  # the job says why; the API lists it as failed
        log.exception("import %s failed", args.job_id)
        try:
            massive_store.update(args.job_id, status="failed", stage=None, stages=None, error=str(exc) or type(exc).__name__)
        except Exception:
            log.exception("import %s: could not mark it failed", args.job_id)
        return 1
    log.info("import %s complete", args.job_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
