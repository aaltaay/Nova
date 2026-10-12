#!/usr/bin/env python3
"""Rank every target choice the eyes scored side by side (#845, operator ask 2026-10-12).

Each trigger's row carries the template's exit and every target choice beside it -- a fixed 10c, 20c and
30c, the next level of today's map, the pullback's high, the high of day and the menu's default pair --
each on the same stop and bailout (``backend/setup_scanner/target_choices.py``). This ranks them on the
triggers from a start date: the count, the win share, the mean and the sum of R before costs and after a
stated cost a share a fill, and how often a choice fell back to the fixed amount. Below the minimum count
it states, it names no leader (``backend/eyes/target_readout.py``).

Usage:

  py -3 tools/target_readout.py --from 2026-10-13 [--setup first_pullback|all] [--template ID|all]
                                [--cost 0.01] [--min-n 30] [--db PATH] [--json]
  py -3 tools/target_readout.py --run RUN_ID [--dir BACKTESTS_DIR] [--json]

The live rows are ``setups.db`` (``--db``, else the operator cache's); ``--run`` reads a backtest run's
``setups.jsonl`` instead (a replay of recorded sessions). Read-only: it never writes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from constants_bot import BOT_SCANNER_SETUPS, BOT_SETUP_FIRST_PULLBACK  # noqa: E402
from constants_setups import SETUPS_TARGET_READOUT_COST, SETUPS_TARGET_READOUT_MIN_N  # noqa: E402
from eyes.target_readout import rank, table  # noqa: E402


def _backtests_dir(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    configured = (os.environ.get("NOVA_EYES_DIR") or "").strip()
    if configured:
        return Path(configured) / "backtests"
    if Path("F:/").exists():
        return Path("F:/Nova/eyes/backtests")
    return REPO / "backend" / ".cache" / "eyes" / "backtests"


def _run_rows(folder: Path, run_id: str) -> list[dict]:
    path = folder / run_id / "setups.jsonl"
    if not path.is_file():
        raise SystemExit(f"no run {run_id} under {folder}")
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            print(f"skipped a line of {path.name} that is not JSON", file=sys.stderr)
    return out


def _db_rows(db: str | None, date_from: str, setup: str, template: str | None) -> list[dict]:
    from setup_scanner.store import SetupStore
    from setup_templates.store import get_store

    store = SetupStore(Path(db)) if db else SetupStore()
    try:
        rows: list[dict] = []
        for sid in (BOT_SCANNER_SETUPS if setup == "all" else [setup]):
            where: dict = {"setup_type": sid}
            if template and template != "all":
                where["template_id"] = template
            elif not template:
                t = get_store().in_play(sid)
                where.update(template_id=t.id, template_rev=int(t.rev))
            rows += store.rows(date_from=date_from, **where)
        return rows
    finally:
        store.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--from", dest="date_from", help="the first session date counted, YYYY-MM-DD")
    ap.add_argument("--setup", default=BOT_SETUP_FIRST_PULLBACK, help="a setup with a scanner, or 'all'")
    ap.add_argument("--template", help="a template id, 'all', or empty for each setup's template in play")
    ap.add_argument("--cost", type=float, default=SETUPS_TARGET_READOUT_COST, help="dollars a share a fill")
    ap.add_argument("--min-n", type=int, default=SETUPS_TARGET_READOUT_MIN_N,
                    help="no leader with fewer scored triggers a choice")
    ap.add_argument("--db", help="setups.db to read (default: the operator cache's)")
    ap.add_argument("--run", help="a backtest run id: read its setups.jsonl instead")
    ap.add_argument("--dir", help="the backtests folder for --run")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.run:
        rows = _run_rows(_backtests_dir(args.dir), args.run)
        if args.date_from:
            rows = [r for r in rows if str(r.get("session_date") or r.get("date") or "") >= args.date_from]
    elif args.date_from:
        rows = _db_rows(args.db, args.date_from, args.setup, args.template)
    else:
        ap.error("--from YYYY-MM-DD (or --run RUN_ID) is needed")
    result = rank(rows, cost=args.cost, min_n=args.min_n)
    print(json.dumps(result, indent=2) if args.json else table(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
