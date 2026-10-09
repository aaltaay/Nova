"""The five-year test of one short setup (ADR 049 section 12, step 4). Run on the desk, after
``select_shorts.py`` and ``research/orb/extract_minutes.py --selection shorts_selection --table minutes_shorts
--start 04:00``.

It tests the rules of the setup's template in play (``--template`` names another) and writes the result file the
setup's card and its On lock read (``setup_scanner.short_tests``): ``running`` first, with its progress, and the
verdict last, each through a temporary file and a rename. The verdict is gate 1's kill criteria on the trades the
scanner's own detectors and scoring took (``short_sim``): at least 300 trades, still positive with the best year
removed, a profit factor over 1 at twice the costs, a neighbourhood that is mostly positive, and a permutation p of
0.05 or less. Beside it the file keeps ``fixed_size``, the same trades on a fixed account, so a trigger after a
losing run is still scored; it is a readout and never decides (ADR 049 amendment, 2026-10-09). Nothing here places
an order, touches a Nova account or changes a setting.

Usage:
    py -3 research/shorts/test_shorts.py --setup bear_flag [--workers 16] [--template ID]
    py -3 research/shorts/test_shorts.py --setup bear_flag --dry-run --days 20      # a look, no result file
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import shorts_config as cfg
import short_sim as sim

ET = ZoneInfo("America/New_York")
SSR_OFF = "off"


# -- the rules under test --------------------------------------------------------------------------------
def resolve(overrides: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    """A neighbour's values: ``"x0.75"`` scales the base value, ``"-30"`` moves a time by minutes."""
    out: dict[str, Any] = {}
    for key, value in overrides.items():
        if isinstance(value, str) and value.startswith("x"):
            out[key] = round(float(base[key]) * float(value[1:]), 4)
        elif isinstance(value, str) and value.lstrip("+-").isdigit() and ":" in str(base.get(key, "")):
            minutes = sim._hm(base[key]) + int(value)
            out[key] = f"{minutes // 60:02d}:{minutes % 60:02d}"
        else:
            out[key] = value
    return out


def variants(template: Any) -> tuple[list[tuple[str, Any]], list[str]]:
    """``[(name, LaneParams)]``: the template's own rules first, then its named neighbourhood; and what was left
    out (a neighbour whose keys the setup does not have)."""
    from setup_scanner.lane_params import lane_params
    from setup_templates import catalogue
    from setup_templates.store import Template

    out = [("base", lane_params(template))]
    left_out: list[str] = []
    keys = {spec.key for spec in catalogue.specs(template.setup)}
    for i, (name, over) in enumerate((*cfg.COMMON_NEIGHBOURS, *cfg.NEIGHBOURS.get(template.setup, ())), 1):
        if not set(over) <= keys:
            left_out.append(f"{name}: {template.setup} has no {', '.join(sorted(set(over) - keys))}")
            continue
        values = catalogue.validate(template.setup, resolve(over, template.values), base=template.values)
        t = Template(setup=template.setup, id=f"n{i:02d}", name=name, rev=1, values=values)
        out.append((name, lane_params(t)))
    return out, left_out


# -- the data ------------------------------------------------------------------------------------------
def _epoch(d: Any, t: Any) -> float:
    return datetime.combine(d, t, ET).timestamp()


def follow_from(bars: list[Any], up10_ts: int | None, from_open: bool) -> float | None:
    """When the scanner followed it: at 04:00 (Former Momo, for the SSR bounce), else the minute after the first
    minute by whose close its high had reached +10% and its volume today 100,000 shares -- never inside the minute
    that met them, which would read its close early. None when it never met both."""
    if not bars:
        return None
    if from_open:
        return bars[0].t
    if up10_ts is None:
        return None
    up10_minute = float(up10_ts) // 60 * 60
    total = 0.0
    for b in bars:
        total += b.v
        if b.t >= up10_minute and total >= cfg.FOLLOW_MIN_VOLUME:
            return b.t + 60
    return None


def load_days(con: Any, setup: str, limit: int | None = None) -> list[tuple[str, list[tuple]]]:
    """``[(day, selection rows)]`` in date order: the SSR bounce takes Former Momo too, the breakdowns movers only."""
    rows = con.execute(f"SELECT d, ticker, prior_close, up10_ts, mover, former_momo, ssr_yesterday "
                       f"FROM {cfg.SELECTION_TABLE} ORDER BY d, ticker").fetchall()
    days: dict[str, list[tuple]] = {}
    for r in rows:
        if setup != "ssr_bounce" and not r[4]:
            continue
        days.setdefault(str(r[0]), []).append(r)
    out = sorted(days.items())
    return out[:limit] if limit else out


def stock_days(con: Any, day: str, rows: list[tuple], setup: str) -> list[sim.StockDay]:
    from setup_scanner.bars import Bar

    tickers = [r[1] for r in rows]
    marks = ", ".join("?" for _ in tickers)
    found: dict[str, list[Bar]] = {}
    for tk, d, t, o, h, lo, c, v in con.execute(
            f"SELECT ticker, d, t, open, high, low, close, volume FROM {cfg.MINUTES_TABLE} "
            f"WHERE d = ?::DATE AND ticker IN ({marks}) ORDER BY ticker, t", [day, *tickers]).fetchall():
        found.setdefault(tk, []).append(Bar(_epoch(d, t), float(o), float(h), float(lo), float(c), float(v or 0)))
    out: list[sim.StockDay] = []
    for _d, tk, prior, up10, _mover, former, ssr_y in rows:
        bars = found.get(tk) or []
        start = follow_from(bars, up10, setup == "ssr_bounce" and bool(former))
        if start is None:
            continue
        if setup == "ssr_bounce" and ssr_y is not True and not (
                prior and min(b.lo for b in bars) <= prior * (1 - cfg.SSR_DROP) + 1e-9):
            continue                                    # SSR is never on: the SSR bounce cannot arm
        out.append(sim.StockDay(tk, day, prior, start, ssr_y, tuple(bars)))
    return out


# -- the result file ----------------------------------------------------------------------------------------
class Result:
    def __init__(self, setup: str, template: Any, command: str, dry_run: bool):
        from setup_scanner import short_tests

        self.path = short_tests.path_of(setup)
        self.dry_run = dry_run
        now = time.time()
        self.body: dict[str, Any] = {
            "schema_version": 1, "setup": setup, "state": "running", "started_at": now, "updated_at": now,
            "finished_at": None, "harness": {"version": cfg.HARNESS_VERSION, "command": command},
            "rules": {"template_id": template.id, "template_rev": int(template.rev),
                      "rules_hash": template.fingerprint},
            "data": None, "assumptions": list(cfg.ASSUMPTIONS), "progress": None, "main": None, "fixed_size": None,
            "ssr_days": None, "criteria": None, "passed": None, "error": None,
        }

    def write(self, **fields: Any) -> None:
        self.body.update(fields, updated_at=time.time())
        if self.dry_run:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.body, indent=1, default=str, allow_nan=False), encoding="utf-8")
        os.replace(tmp, self.path)


# -- the verdict -------------------------------------------------------------------------------------------
def criteria(setup: str, by_variant: dict[str, list[sim.Trade]], days_of: Any, rules: list[tuple[str, Any]],
             progress: Any) -> tuple[dict, dict, dict | None, dict]:
    """``(main, fixed_size, ssr_days, criteria)`` from every variant's trades. ``fixed_size`` is ``main``'s trades
    on the fixed account: a readout no criterion reads (ADR 049 amendment, 2026-10-09)."""
    from constants_bot import BOT_SHORT_BREAKDOWN_SETUPS

    apart = setup in BOT_SHORT_BREAKDOWN_SETUPS

    def pool(trades: list[sim.Trade]) -> list[sim.Trade]:
        return [t for t in trades if t.ssr == SSR_OFF] if apart else list(trades)

    base_trades = pool(by_variant["base"])
    costed = sim.account(base_trades)
    main = sim.stats(costed)
    fixed_size = sim.stats(sim.account(base_trades, sim.FIXED))
    ssr_days = sim.stats(sim.account([t for t in by_variant["base"] if t.ssr != SSR_OFF])) if apart else None
    doubled = sim.stats(sim.account(base_trades, sim.DOUBLE))
    neighbours = []
    for name, _params in rules[1:]:
        s = sim.stats(sim.account(pool(by_variant[name])))
        neighbours.append({"name": name, "trades": s["trades"], "exp_r": s["exp_r"],
                           "positive": s["exp_r"] is not None and s["exp_r"] > 0})
    positive = sum(1 for n in neighbours if n["positive"])
    days = {(t.ticker, t.d): None for t in base_trades}
    perm = sim.shuffle(base_trades, days_of(list(days)), rules[0][1], progress=progress)
    crit = {
        "trades": {"value": main["trades"], "need": cfg.MIN_TRADES, "ok": main["trades"] >= cfg.MIN_TRADES},
        "best_year_removed": sim.best_year_removed(costed),
        "costs_2x": {"pf": doubled["pf"], "no_losses": doubled["no_losses"],
                     "ok": doubled["no_losses"] or (doubled["pf"] is not None and doubled["pf"] > 1)},
        "neighbourhood": {"variants": neighbours, "positive": positive, "total": len(neighbours),
                          "ok": bool(neighbours) and positive > len(neighbours) / 2},
        "permutation": perm,
    }
    return main, fixed_size, ssr_days, crit


def main() -> int:
    from common import connect, load_env

    load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--setup", required=True)
    ap.add_argument("--template", help="a template id (default: the template in play)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--dry-run", action="store_true", help="print only; write no result file")
    ap.add_argument("--days", type=int, help="the first N days only (with --dry-run)")
    a = ap.parse_args()
    from constants_bot import BOT_SHORT_SETUPS
    from setup_templates.store import get_store

    if a.setup not in BOT_SHORT_SETUPS:
        raise SystemExit(f"--setup is one of {', '.join(BOT_SHORT_SETUPS)}")
    if a.days and not a.dry_run:
        raise SystemExit("--days is for a look: add --dry-run (a verdict reads every day)")
    store = get_store()
    template = store.get(a.setup, a.template) if a.template else store.in_play(a.setup)
    command = " ".join(["py -3 research/shorts/test_shorts.py", *sys.argv[1:]])
    result = Result(a.setup, template, command, a.dry_run)
    try:
        rules, left_out = variants(template)
        why = sim.untestable(rules[0][1])
        if why:
            raise ValueError(why)      # the result reads `error`: On stays locked, never a pass on untested exits
        con = connect(read_only=True)
        days = load_days(con, a.setup, a.days)
        result.write(assumptions=[*cfg.ASSUMPTIONS, *(f"Neighbour left out -- {x}" for x in left_out)],
                     progress={"done": 0, "total": len(days), "unit": "days"})
        by_variant: dict[str, list[sim.Trade]] = {name: [] for name, _ in rules}
        n_days = 0
        with ProcessPoolExecutor(max_workers=a.workers) as pool:
            running: set[Any] = set()
            todo = iter(days)
            while True:
                while len(running) < 2 * a.workers:      # a bounded queue: only a few days' bars in memory
                    nxt = next(todo, None)
                    if nxt is None:
                        break
                    running.add(pool.submit(sim.run_day, (stock_days(con, nxt[0], nxt[1], a.setup), rules)))
                if not running:
                    break
                done, running = wait(running, return_when=FIRST_COMPLETED)
                for fut in done:
                    for name, trades in fut.result().items():
                        by_variant[name].extend(trades)
                    n_days += 1
                    if n_days % 25 == 0 or n_days == len(days):
                        result.write(progress={"done": n_days, "total": len(days), "unit": "days"})
        n_symbol_days = sum(len(rows) for _d, rows in days)

        def days_of(keys: list[tuple[str, str]]) -> dict[tuple[str, str], sim.StockDay]:
            out: dict[tuple[str, str], sim.StockDay] = {}
            wanted: dict[str, set[str]] = {}
            for tk, d in keys:
                wanted.setdefault(d, set()).add(tk)
            for d, rows in days:
                if d in wanted:
                    for sd in stock_days(con, d, [r for r in rows if r[1] in wanted[d]], a.setup):
                        out[(sd.ticker, sd.d)] = sd
            return out

        def shuffled(k: int, total: int) -> None:
            if k % 50 == 0 or k == total:
                result.write(progress={"done": k, "total": total, "unit": "shuffles"})

        main_s, fixed_s, ssr_s, crit = criteria(a.setup, by_variant, days_of, rules, shuffled)
        passed = all(c.get("ok") for c in crit.values())
        result.write(state="passed" if passed else "failed", passed=passed, finished_at=time.time(), main=main_s,
                     fixed_size=fixed_s, ssr_days=ssr_s, criteria=crit, progress=None,
                     data={"first_day": days[0][0] if days else None, "last_day": days[-1][0] if days else None,
                           "days": n_days, "symbol_days": n_symbol_days})
        print(json.dumps({k: result.body[k] for k in ("state", "main", "fixed_size", "criteria")}, indent=1,
                         default=str))
        print("dry run: no result file written" if a.dry_run else f"written: {result.path}")
        return 0
    except Exception as exc:
        traceback.print_exc()
        result.write(state="error", passed=None, finished_at=time.time(), error=f"{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
