"""The target choices ranked (#845, operator ask 2026-10-12): which target would have paid, on the same triggers.

Every trigger's row carries every target choice scored side by side (``setup_scanner/target_choices.py``:
``target_scores``). This reads the rows from a start date and ranks the choices by their mean R net of a
stated cost a share a fill -- with the count, the win share, the mean and the sum of R before costs and
after, and how often each fell back to the fixed amount. It never names a leader with fewer than
``min_n`` scored triggers in every choice: below it the answer says how many it has and how many it needs.

R is the risk a share (1R = the stop's distance): the unit the scores are measured in, never a target.
Pure: rows in, a dict out.
"""
from __future__ import annotations

from typing import Any, Iterable

from constants_setups import (
    SETUPS_TARGET_CHOICES_SCHEMA_VERSION,
    SETUPS_TARGET_READOUT_COST,
    SETUPS_TARGET_READOUT_MIN_N,
)
from setup_scanner.summary import net_r
from setup_scanner.target_choices import NAMES

READOUT_SCHEMA_VERSION = 1


def _scores(row: dict[str, Any]) -> dict[str, Any] | None:
    got = row.get("target_scores")
    if not isinstance(got, dict) or got.get("schema_version") != SETUPS_TARGET_CHOICES_SCHEMA_VERSION:
        return None
    return got


def _mean(vals: list[float]) -> float | None:
    return round(sum(vals) / len(vals), 3) if vals else None


def rank(rows: Iterable[dict[str, Any]], *, cost: float = SETUPS_TARGET_READOUT_COST,
         min_n: int = SETUPS_TARGET_READOUT_MIN_N) -> dict[str, Any]:
    """``{schema_version, cost, min_n, triggers, scored, choices: [...], leader, note}`` -- ``choices`` best
    first by mean net R (a choice without a scored trigger last), each ``{name, n, wins, win_pct, mean_r,
    sum_r, mean_net_r, sum_net_r, fell_back, open}``."""
    per: dict[str, dict[str, Any]] = {n: {"r": [], "net": [], "fell_back": 0, "open": 0} for n in NAMES}
    triggers = scored = 0
    for row in rows:
        if not row.get("triggered_at"):
            continue
        sc = _scores(row)
        if sc is None:
            continue
        triggers += 1
        risk = sc.get("risk") or row.get("risk")
        any_scored = False
        for name, c in (sc.get("choices") or {}).items():
            slot = per.setdefault(name, {"r": [], "net": [], "fell_back": 0, "open": 0})
            if c.get("fell_back"):
                slot["fell_back"] += 1
            if c.get("bar_r") is None:
                slot["open"] += 1
                continue
            any_scored = True
            slot["r"].append(float(c["bar_r"]))
            net = net_r({"bar_r": c["bar_r"], "risk": risk, "exit_reason": c.get("exit_reason")}, cost)
            slot["net"].append(float(net) if net is not None else float(c["bar_r"]))
        scored += any_scored
    out = []
    for name, slot in per.items():
        n = len(slot["r"])
        wins = sum(1 for r in slot["r"] if r > 0)
        out.append({"name": name, "n": n, "wins": wins, "win_pct": round(100 * wins / n, 1) if n else None,
                    "mean_r": _mean(slot["r"]), "sum_r": round(sum(slot["r"]), 3),
                    "mean_net_r": _mean(slot["net"]), "sum_net_r": round(sum(slot["net"]), 3),
                    "fell_back": slot["fell_back"], "open": slot["open"]})
    out.sort(key=lambda c: (c["mean_net_r"] is None, -(c["mean_net_r"] or 0.0), c["name"]))
    fewest = min((c["n"] for c in out), default=0)
    leader = out[0]["name"] if out and fewest >= min_n and out[0]["mean_net_r"] is not None else None
    if leader:
        note = (f"{leader} leads on {fewest} or more scored triggers a choice, net of {cost:.2f} a share a fill. "
                "A lead is a description: nothing changes a template on it.")
    else:
        note = (f"No leader: the fewest scored triggers of a choice is {fewest}; the read-out names one from "
                f"{min_n}.")
    return {"schema_version": READOUT_SCHEMA_VERSION, "cost": cost, "min_n": min_n, "triggers": triggers,
            "scored": scored, "choices": out, "leader": leader, "note": note}


def table(result: dict[str, Any]) -> str:
    """The ranking as plain text (the tool's)."""
    head = f"{'choice':<16}{'n':>5}{'win%':>7}{'mean R':>9}{'sum R':>9}{'net mean':>10}{'net sum':>9}{'fell back':>11}"
    lines = [head, "-" * len(head)]
    for c in result["choices"]:
        def f(x: Any, fmt: str) -> str:
            return "--" if x is None else format(x, fmt)
        lines.append(f"{c['name']:<16}{c['n']:>5}{f(c['win_pct'], '.1f'):>7}{f(c['mean_r'], '+.3f'):>9}"
                     f"{f(c['sum_r'], '+.2f'):>9}{f(c['mean_net_r'], '+.3f'):>10}{f(c['sum_net_r'], '+.2f'):>9}"
                     f"{c['fell_back']:>11}")
    lines.append("")
    lines.append(f"{result['triggers']} triggers with scores, {result['scored']} scored; cost {result['cost']:.2f} a "
                 f"share a fill. {result['note']}")
    return "\n".join(lines)
