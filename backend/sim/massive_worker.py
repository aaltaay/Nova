"""One Massive import, run out of the API process (ADR 046).

    python -m sim.massive_worker --job-id ID
    nova-api.exe --massive-import --job-id ID      (the frozen desk)

An import inflates gigabytes and parses a ticker's rows for seconds to minutes. In
the API process that work would share the GIL with the event loops that carry the
desk's Level 2, tape and orders (ADR 045), so it runs here, below normal priority,
and talks to the API only through the Massive store: the job's progress and its end.
The API pauses an import by ending this process; nothing is written before the
window's final transaction, so an ended import leaves no partial window. After the
job is complete the process builds the indexes of the day files it read without
one (``massive_index``); a new import of another day ends it then, losing only
that build.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from constants_sim import SIM_MASSIVE_WORKER_MEMORY_ENV, SIM_MASSIVE_WORKER_MEMORY_MB


def _lower_priority() -> None:
    try:
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.kernel32.SetPriorityClass(ctypes.c_void_p(-1), 0x00004000)   # BELOW_NORMAL_PRIORITY_CLASS
        else:
            os.nice(10)
    except Exception:
        logging.getLogger(__name__).warning("massive import: could not lower its priority", exc_info=True)


def _cap_memory() -> int | None:
    """Cap this import's committed memory (``SIM_MASSIVE_WORKER_MEMORY_MB``): a read that keeps too much fails
    this import, never the PC. The cap in MB, or None when there is none (off Windows, set to 0, or refused --
    logged, never assumed)."""
    log = logging.getLogger(__name__)
    raw = os.environ.get(SIM_MASSIVE_WORKER_MEMORY_ENV, "").strip()
    try:
        cap_mb = int(raw) if raw else SIM_MASSIVE_WORKER_MEMORY_MB
    except ValueError:
        log.warning("massive import: %s=%r is not a whole number of MB; the cap stays %d MB",
                    SIM_MASSIVE_WORKER_MEMORY_ENV, raw, SIM_MASSIVE_WORKER_MEMORY_MB)
        cap_mb = SIM_MASSIVE_WORKER_MEMORY_MB
    if cap_mb <= 0:
        log.warning("massive import: no memory cap (%s=%s)", SIM_MASSIVE_WORKER_MEMORY_ENV, raw)
        return None
    try:
        from winapi import job_limit

        if not job_limit.cap_this_process(cap_mb * 2**20):
            return None
    except Exception:
        log.warning("massive import: could not cap its memory at %d MB; it runs uncapped", cap_mb, exc_info=True)
        return None
    log.info("massive import: memory capped at %d MB", cap_mb)
    return cap_mb


def why_failed(exc: BaseException, cap_mb: int | None) -> str:
    """The job's ``error``: a cap the import ran into says so, with the setting that raises it."""
    if isinstance(exc, MemoryError) and cap_mb:
        return (f"The import used its whole {cap_mb:,} MB memory cap and was stopped before writing anything "
                f"({SIM_MASSIVE_WORKER_MEMORY_ENV} raises it)")
    return str(exc) or type(exc).__name__


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
    cap_mb = _cap_memory()
    from sim import massive_import, massive_store

    log = logging.getLogger("sim.massive_worker")
    log.info("import %s starts (pid %s)", args.job_id, os.getpid())
    try:
        massive_import.run(args.job_id)
    except Exception as exc:  # the job says why; the API lists it as failed
        log.exception("import %s failed", args.job_id)
        try:
            massive_store.update(args.job_id, status="failed", stage=None, stages=None, error=why_failed(exc, cap_mb))
        except Exception:
            log.exception("import %s: could not mark it failed", args.job_id)
        return 1
    log.info("import %s complete", args.job_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
