"""What the Sim eyes follow now (ADR 029, ADR 052): the Sim desk's replay and its playhead.

- ``capture``: a Session Record is loaded -- today's templates re-read it.
- ``history``: a historical window is loaded (a Massive window or an IBKR download) -- today's
  templates re-read it too (``eyes.history_recording``), so the board, the charts and Nova's bot
  read one source: the replay the scratch account fills against.
- ``journal``: nothing is loaded off the live edge -- what Nova's live eyes recorded at the
  playhead's day (``eyes/playback.py``).
- ``None``: the live edge, or another venue: the live board stays.

Every target names the playhead and, for a loaded replay, ``replay_key``: the scratch account's
own key (``sim.practice.loaded``), which the triggers carry so Nova's bot trades only the replay
the desk is on. Reads only.
"""
from __future__ import annotations

from typing import Any

KIND_CAPTURE = "capture"
KIND_HISTORY = "history"
KIND_JOURNAL = "journal"
LANE_KINDS = (KIND_CAPTURE, KIND_HISTORY)


def replay_key() -> list | None:
    """The loaded replay's key as the scratch account names it; None when nothing is loaded."""
    from sim import practice

    loaded = practice.loaded()
    return list(loaded.key) if loaded is not None else None


def default_target() -> dict[str, Any] | None:
    """What the Sim desk shows now: ``None`` at the live edge or off the Sim venue."""
    from sim.mode import is_replay_desk

    if not is_replay_desk():
        return None
    from sim import replay as sim_replay
    from sim import session_clock

    st = sim_replay.status_payload()
    playhead = session_clock.now_et().timestamp()
    source = st.get("replay_source")
    if source == "capture" and st.get("replay_ok"):
        return {"kind": KIND_CAPTURE, "date": st.get("replay_date"), "symbol": st.get("replay_symbol"),
                "playhead": playhead, "key": ("capture", st.get("replay_date"), str(st.get("replay_symbol")).upper()),
                "replay_key": replay_key()}
    if source == "historical" and st.get("replay_ok"):
        from eyes.history_recording import key_of
        from sim import history_playback

        spec = history_playback.status()
        if spec:
            return {"kind": KIND_HISTORY, "date": spec.get("date"), "symbol": str(spec.get("symbol")).upper(),
                    "playhead": playhead, "key": key_of(spec), "replay_key": replay_key(),
                    "source": spec.get("source") or "ibkr"}
    at = session_clock.now_et()
    loaded = source if source in ("historical", "capture") else None
    return {"kind": KIND_JOURNAL, "date": at.strftime("%Y-%m-%d"), "playhead": playhead,
            "symbol": st.get("replay_symbol") if loaded else None, "loaded": loaded}
