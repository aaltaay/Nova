"""What a stored Massive import holds, and whether its stock-day is to be read again (ADR 046).

Pure reads of an import's job (``massive_store``) and of what the day's files hold
(``massive_import.availability``); ``massive_import`` owns the jobs and the import
process that act on them.

An import is read again -- its window keeps playing until the new read replaces it --
when something is on disk it lacks (its quotes, or the day's 1-minute bars), when it was
cut under a smaller cap than the one ``massive_read`` applies now (500,000 prints before
2026-10-14, so its day may fit whole now), or when it was stored as a row per print
before the store packed them (schema 2), which loads slowly.
"""
from __future__ import annotations

from constants_sim import SIM_MASSIVE_MINUTES_SCOPE_DAY
from sim import massive_read


def kept_bounds(job: dict) -> tuple[float, float] | None:
    """What an import holds, epoch seconds: its ``ranges`` (the day, or a capped day's focus); None before it completes."""
    ranges = job.get("ranges") or []
    if not ranges:
        return None
    return min(a for a, _b in ranges), max(b for _a, b in ranges)


def holds(job: dict | None, window: dict) -> bool:
    """The import holds ``window``, read up to the import's own bounds (nothing trades outside the session)."""
    kept = kept_bounds(job) if job is not None else None
    if kept is None:
        return False
    lo, hi = max(window["start_ts"], job["start_ts"]), min(window["end_ts"], job["end_ts"])
    return kept[0] <= lo and hi <= kept[1]


def quotes_arrived(job: dict, found: dict) -> bool:
    """A window imported before its day's quotes were on disk, whose quotes now are."""
    return job.get("quote_status") == "not_downloaded" and found["quotes"]


def day_minutes_missing(job: dict, found: dict) -> bool:
    """A window imported when an import kept only its own 1-minute bars, whose day's bars file is on disk."""
    return job.get("minutes_scope") != SIM_MASSIVE_MINUTES_SCOPE_DAY and found["minute_aggs"]


def more_on_disk(job: dict, found: dict) -> bool:
    return quotes_arrived(job, found) or day_minutes_missing(job, found)


def cap_raised(job: dict) -> bool:
    """A capped import whose dataset's cap has been raised since (2026-10-14): its day may fit whole now."""
    cap = job.get("capped")
    if not cap:
        return False
    # The caps the import applies now (``massive_read``'s), the ones a new read would be held to.
    limit = (massive_read.SIM_HISTORY_MAX_SELECTION_PRINTS if cap.get("what") == "prints"
             else massive_read.SIM_MASSIVE_MAX_SELECTION_QUOTES)
    return int(cap.get("limit") or 0) < limit


def stored_as_rows(job: dict) -> bool:
    """A complete import stored a row per print (before schema 2): it plays, but loads slowly."""
    return job.get("status") == "complete" and not job.get("packed")


def import_again(job: dict, found: dict) -> bool:
    """Read the stock-day again: something is on disk it lacks, its cap was raised, or it is stored as rows."""
    return more_on_disk(job, found) or cap_raised(job) or stored_as_rows(job)
