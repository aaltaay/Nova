"""Per-session timestamp admission and event-time L2 coalescing (ADR 001)."""
from copy import deepcopy
from pathlib import Path
import json

from capture.constants_capture import CAPTURE_L2_MAX_HZ, CAPTURE_STREAM_NAMES
from capture.schema import validate_version, valid_timestamp


class Fidelity:
    def __init__(self):
        self.last_ts = {}
        self.invalid_timestamp_rows = 0
        self.timestamp_regressions = 0
        self.l2_offered = 0
        self.l2_coalesced = 0
        self.last_l2_ts = None
        self.pending_l2 = None

    def seed(self, root: Path, prior: dict):
        saved = prior.get("fidelity") or {}
        for key in ("invalid_timestamp_rows", "timestamp_regressions", "l2_offered", "l2_coalesced"):
            setattr(self, key, max(0, int(saved.get(key) or 0)))
        # Resume is worker-owned, never a hot path. Stream every existing row
        # so an incompatible version in the middle cannot be silently appended.
        for name in CAPTURE_STREAM_NAMES:
            path = root / (name + ".jsonl")
            if not path.is_file():
                continue
            with path.open("rb") as stream:
                for raw in stream:
                    try:
                        row = json.loads(raw)
                    except (ValueError, UnicodeError):
                        continue  # Replay reports malformed rows; never fabricate one.
                    if not isinstance(row, dict):
                        continue
                    validate_version(row)
                    ts = row.get("ts")
                    if valid_timestamp(ts):
                        self.last_ts[name] = max(ts, self.last_ts.get(name, ts))

    def admit(self, kind: str, row: dict) -> str | None:
        ts = row.get("ts")
        if not valid_timestamp(ts):
            self.invalid_timestamp_rows += 1
            return "Invalid capture timestamp; recording stopped"
        if ts < self.last_ts.get(kind, ts):
            self.timestamp_regressions += 1
            return "Capture timestamp moved backwards; recording stopped before overlapping data"
        self.last_ts[kind] = ts
        return None

    def offer_l2(self, row: dict) -> dict | None:
        self.l2_offered += 1
        if self.pending_l2 is not None:
            self.l2_coalesced += 1
        self.pending_l2 = deepcopy(row)
        if self.last_l2_ts is None or row["ts"] - self.last_l2_ts >= 1 / CAPTURE_L2_MAX_HZ:
            return self.drain_l2()
        return None

    def drain_l2(self) -> dict | None:
        row, self.pending_l2 = self.pending_l2, None
        if row is not None:
            self.last_l2_ts = row["ts"]
        return row

    def payload(self) -> dict:
        return {"l2_offered": self.l2_offered, "l2_coalesced": self.l2_coalesced,
                "l2_max_hz": CAPTURE_L2_MAX_HZ,
                "invalid_timestamp_rows": self.invalid_timestamp_rows,
                "timestamp_regressions": self.timestamp_regressions,
                "last_stream_ts": dict(self.last_ts)}
