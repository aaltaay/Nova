"""Does the tape flow score say anything about the next minutes? (ADR 034)

For every second of every recorded stretch of a Session Record, read the tape
flow (``tape_flow.FlowIndex``: the lanes' own rule) and the mid price -- the
recorded book's, else the last price-setting print -- and measure where the mid
went over each horizon. Seconds overlap heavily (a flush lasts many of them), so
the verdict rests on **onsets**: the first second of a burst or a flush after
``refractory`` seconds without one, each counted once. A horizon that runs past
the end of its recorded stretch is not measured: a gap is never read as a price.

Moves are in basis points of the mid (1 bp = 0.01%); the spread at each onset is
reported beside them, so a move smaller than the cost of crossing the spread is
visible as such. ``t`` is the mean over its standard error -- a rough guide on
overlapping samples, never a proof.

``onsets_by_context`` splits the onsets by where the mid went in the
``context_sec`` before them -- ``after_rise`` / ``after_fall`` / ``flat`` -- the
question a flush exit asks: does a flush after a run-up keep falling?

Pure apart from what the caller loads: recordings in, numbers out. Owner of no
file; ``tools/flow_study.py`` prints it and writes it only where it is told to.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from constants_eyes import (
    EYES_FLOW_STUDY_BUCKET,
    EYES_FLOW_STUDY_CONTEXT_BP,
    EYES_FLOW_STUDY_CONTEXT_SEC,
    EYES_FLOW_STUDY_HORIZONS_SEC,
    EYES_FLOW_STUDY_REFRACTORY_SEC,
    EYES_FLOW_STUDY_STEP_SEC,
    EYES_SCHEMA_VERSION,
)
from constants_setups import TAPE_FLOW_BURST, TAPE_FLOW_FLUSH, TAPE_FLOW_LABELS
from setup_scanner.tape_flow import FlowIndex, FlowParams

ONSET_LABELS = (TAPE_FLOW_BURST, TAPE_FLOW_FLUSH)


@dataclass(frozen=True)
class StudyParams:
    horizons: tuple[int, ...] = EYES_FLOW_STUDY_HORIZONS_SEC
    step_sec: float = EYES_FLOW_STUDY_STEP_SEC
    refractory_sec: float = EYES_FLOW_STUDY_REFRACTORY_SEC
    bucket: float = EYES_FLOW_STUDY_BUCKET
    context_sec: float = EYES_FLOW_STUDY_CONTEXT_SEC
    context_bp: float = EYES_FLOW_STUDY_CONTEXT_BP


def _mid(idx: FlowIndex, t: float, p: FlowParams, since: float) -> tuple[float | None, float | None]:
    """``(mid, spread in bp)`` at ``t``: the fresh book's, else the last price since ``since`` (no spread)."""
    _b, _a, bid, ask = idx.depth_at(t, p)
    if bid is not None and ask is not None and 0 < bid <= ask:
        mid = (bid + ask) / 2
        return mid, (ask - bid) / mid * 1e4
    return idx.last_price(t, since=since), None


def samples(rec: Any, p: FlowParams, sp: StudyParams = StudyParams(), idx: FlowIndex | None = None) -> list[dict]:
    """One reading per ``step_sec`` of each recorded stretch, with where the mid went after it."""
    idx = idx or FlowIndex(rec.prints, rec.books)
    spans = list(rec.spans) or ([(rec.first_ts, rec.last_ts)] if rec.first_ts is not None else [])
    out: list[dict] = []
    for a, b in spans:
        a, b = float(a), float(b)
        t0 = math.ceil(a + p.window_sec)
        steps = int((b - t0) // sp.step_sec) + 1 if b >= t0 else 0
        mids: list[float | None] = []
        rows: list[dict] = []
        for k in range(steps):
            t = t0 + k * sp.step_sec
            flow = idx.evaluate(t, p, history_from=a)
            mid, spread = _mid(idx, t, p, a)
            mids.append(mid)
            rows.append({"ts": t, "label": flow["label"], "score": flow["score"], "mid": mid, "spread_bp": spread})
        back_steps = int(round(sp.context_sec / sp.step_sec))
        for k, row in enumerate(rows):
            m_back = mids[k - back_steps] if k >= back_steps else None
            row["back_bp"] = None if not m_back or not row["mid"] else (row["mid"] / m_back - 1.0) * 1e4
            fwd: dict[int, float | None] = {}
            for h in sp.horizons:
                j = k + int(round(h / sp.step_sec))
                m0 = row["mid"]
                m1 = mids[j] if j < len(mids) else None
                fwd[h] = None if not m0 or m1 is None else (m1 / m0 - 1.0) * 1e4
            row["fwd"] = fwd
        out += rows
    return out


def _stats(values: list[float]) -> dict[str, Any]:
    n = len(values)
    if not n:
        return {"n": 0, "mean_bp": None, "median_bp": None, "up_pct": None, "t": None}
    mean = sum(values) / n
    ordered = sorted(values)
    median = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1)) if n > 1 else 0.0
    return {"n": n, "mean_bp": round(mean, 2), "median_bp": round(median, 2),
            "up_pct": round(100 * sum(1 for v in values if v > 0) / n, 1),
            "t": round(mean / (sd / math.sqrt(n)), 2) if sd > 0 else None}


def _bucket(score: float | None, width: float) -> str:
    if score is None:
        return "none"
    lo = max(-1.0, min(1.0 - width, math.floor(score / width) * width))
    return f"{lo:+.2f}..{lo + width:+.2f}"


def _bucket_order(name: str) -> float:
    """Buckets from the most selling to the most buying; ``none`` (no score) last."""
    return float(name.split("..")[0]) if name != "none" else 9.0


def context(back_bp: float | None, threshold_bp: float) -> str:
    if back_bp is None:
        return "unknown"
    return "after_rise" if back_bp >= threshold_bp else "after_fall" if back_bp <= -threshold_bp else "flat"


def onsets(rows: list[dict], refractory_sec: float) -> list[dict]:
    """The first second of each burst / flush after ``refractory_sec`` without one of its kind."""
    last_seen: dict[str, float] = {}
    out = []
    for row in rows:
        label = row["label"]
        if label not in ONSET_LABELS:
            continue
        prev = last_seen.get(label)
        if prev is None or row["ts"] - prev > refractory_sec:
            out.append(row)
        last_seen[label] = row["ts"]
    return out


def aggregate(per_recording: list[tuple[str, list[dict]]], p: FlowParams,
              sp: StudyParams = StudyParams()) -> dict[str, Any]:
    """Every recording's readings folded into one answer."""
    seconds: dict[str, int] = {k: 0 for k in TAPE_FLOW_LABELS}
    by_label: dict[str, dict[int, list[float]]] = {}
    by_bucket: dict[str, dict[int, list[float]]] = {}
    ons: dict[str, dict[int, list[float]]] = {k: {h: [] for h in sp.horizons} for k in ONSET_LABELS}
    spreads: dict[str, list[float]] = {k: [] for k in ONSET_LABELS}
    by_ctx: dict[str, dict[str, dict[int, list[float]]]] = {k: {} for k in ONSET_LABELS}
    recordings = []
    for name, rows in per_recording:
        mine = onsets(rows, sp.refractory_sec)
        recordings.append({"recording": name, "seconds": len(rows),
                           "onsets": {k: sum(1 for r in mine if r["label"] == k) for k in ONSET_LABELS}})
        for row in rows:
            seconds[row["label"]] = seconds.get(row["label"], 0) + 1
            for h, v in row["fwd"].items():
                if v is None:
                    continue
                by_label.setdefault(row["label"], {}).setdefault(h, []).append(v)
                by_bucket.setdefault(_bucket(row["score"], sp.bucket), {}).setdefault(h, []).append(v)
        for row in mine:
            if row["spread_bp"] is not None:
                spreads[row["label"]].append(row["spread_bp"])
            ctx = by_ctx[row["label"]].setdefault(context(row.get("back_bp"), sp.context_bp), {})
            for h, v in row["fwd"].items():
                if v is not None:
                    ons[row["label"]][h].append(v)
                    ctx.setdefault(h, []).append(v)
    onset_stats = {k: {str(h): _stats(v) for h, v in hs.items()} for k, hs in ons.items()}
    separation = {}
    for h in sp.horizons:
        b, f = onset_stats[TAPE_FLOW_BURST][str(h)], onset_stats[TAPE_FLOW_FLUSH][str(h)]
        separation[str(h)] = (round(b["mean_bp"] - f["mean_bp"], 2)
                              if b["mean_bp"] is not None and f["mean_bp"] is not None else None)
    total = sum(seconds.values())
    return {
        "schema_version": EYES_SCHEMA_VERSION,
        "params": asdict(p), "study": asdict(sp), "recordings": recordings, "seconds": total,
        "seconds_by_label": {k: {"n": v, "pct": round(100 * v / total, 1) if total else None}
                             for k, v in seconds.items()},
        "onsets": onset_stats,
        "onset_spread_bp": {k: _stats(v)["median_bp"] for k, v in spreads.items()},
        "onsets_by_context": {k: {c: {str(h): _stats(v) for h, v in sorted(hs.items())} for c, hs in sorted(cs.items())}
                              for k, cs in by_ctx.items()},
        "separation_bp": separation,
        "by_label": {k: {str(h): _stats(v) for h, v in hs.items()} for k, hs in sorted(by_label.items())},
        "by_bucket": {k: {str(h): _stats(v) for h, v in hs.items()}
                      for k, hs in sorted(by_bucket.items(), key=lambda kv: _bucket_order(kv[0]))},
    }


def study(recs: Iterable[Any], p: FlowParams, sp: StudyParams = StudyParams(),
          indexes: dict[str, FlowIndex] | None = None) -> dict[str, Any]:
    """Read every recording under ``p`` and fold them. ``indexes`` reuses built indexes across a grid."""
    per = []
    for rec in recs:
        name = f"{rec.date}:{rec.symbol}"
        idx = (indexes or {}).get(name)
        if idx is None:
            idx = FlowIndex(rec.prints, rec.books)
            if indexes is not None:
                indexes[name] = idx
        per.append((name, samples(rec, p, sp, idx)))
    return aggregate(per, p, sp)
