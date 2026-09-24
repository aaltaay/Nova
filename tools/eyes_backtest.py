#!/usr/bin/env python3
"""Backtest the eyes on Session Records (ADR 029) and read the runs.

A run replays each recording through one lane per first-pullback template --
the same detector, tape gate and scoring as the live eyes -- and keeps every
armed setup with its tape at near and at the trigger and its scores. Runs live
under ``<eyes dir>/backtests/<run_id>/`` and never touch the live scoreboard
or the read-out that gates Strategy.

Usage:

  py -3 tools/eyes_backtest.py run [--template ID ...] [--session 2026-09-23:WHLR ...]
  py -3 tools/eyes_backtest.py sweep [--setup first_pullback] [--base ID] --grid flush_exit=off,tighten,exit
                                     [--grid flow_flush_at=0.4,0.5,0.6] [--set KEY=VALUE ...] [--session ...]
  py -3 tools/eyes_backtest.py list
  py -3 tools/eyes_backtest.py show RUN_ID [--setups]

``sweep`` (ADR 034) runs one variant per grid combination -- templates made for
the run only, the base template's values with those parameters changed, never
stored -- plus the base itself first, on the same recordings; ``show`` then
gives each variant's exits and its R against the base on the same setups.

``run`` asks the running API (``POST /api/eyes/backtests``, with the key from
the repo ``.env``) so it reads the same captures, bar archive and templates as
the desk; ``--local`` runs it in this process instead (only when the API is
down: it opens the archive the API writes). ``list`` / ``show`` read the folder
(``--dir``, else ``NOVA_EYES_DIR``/backtests, else ``F:\\Nova\\eyes\\backtests``,
else ``backend/.cache/eyes/backtests``).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
API = "http://127.0.0.1:8000"


def backtests_dir(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    configured = (os.environ.get("NOVA_EYES_DIR") or "").strip()
    if configured:
        return Path(configured) / "backtests"
    if Path("F:/").exists():
        return Path("F:/Nova/eyes/backtests")
    return REPO / "backend" / ".cache" / "eyes" / "backtests"


def _api_key() -> str:
    key = (os.environ.get("NOVA_API_KEY") or "").strip()
    if key:
        return key
    env = REPO / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("NOVA_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _sessions(raw: list[str] | None) -> list[dict] | None:
    if not raw:
        return None
    out = []
    for item in raw:
        date, _, symbol = item.partition(":")
        out.append({"date": date, "symbol": symbol.upper()})
    return out


def cmd_run(args: argparse.Namespace) -> int:
    body = {"templates": args.template or None, "sessions": _sessions(args.session)}
    if args.local:
        from eyes import backtest

        sessions = [(s["date"], s["symbol"]) for s in body["sessions"]] if body["sessions"] else None
        man = backtest.run(template_ids=body["templates"], sessions=sessions,
                           progress=lambda i, n: print(f"  {i}/{n}", file=sys.stderr))
        print(json.dumps({k: man[k] for k in ("run_id", "status", "error")}, indent=2))
        return 0 if man["status"] == "done" else 1
    req = urllib.request.Request(f"{API}/api/eyes/backtests", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Nova-Api-Key": _api_key()})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(f"refused {exc.code}: {exc.read().decode()}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"the API at {API} did not answer ({exc.reason}); --local runs it here", file=sys.stderr)
        return 1
    return 0


def _post(body: dict) -> int:
    req = urllib.request.Request(f"{API}/api/eyes/backtests", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Nova-Api-Key": _api_key()})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(f"refused {exc.code}: {exc.read().decode()}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"the API at {API} did not answer ({exc.reason}); --local runs it here", file=sys.stderr)
        return 1
    return 0


def sweep_variants(setup: str, base: str, sets: list[str] | None, grids: list[str] | None) -> list[dict]:
    """The base (with ``--set``) first, then one variant per combination of the ``--grid`` values."""
    import itertools

    from setup_templates import catalogue

    def pairs(items, many):
        out = []
        for item in items or []:
            key, sep, raw = item.partition("=")
            if not sep:
                raise SystemExit(f"{item!r} is not KEY=VALUE")
            vals = raw.split(",") if many else [raw]
            out.append((key.strip(), [catalogue.parse_text(setup, key.strip(), v) for v in vals]))
        return out

    fixed = {k: v[0] for k, v in pairs(sets, False)}
    grid = pairs(grids, True)
    variants = [{"name": "base" + (" " + ", ".join(f"{k}={v}" for k, v in fixed.items()) if fixed else ""),
                 "base": base, "values": dict(fixed)}]
    keys = [k for k, _ in grid]
    for combo in itertools.product(*(vs for _, vs in grid)):
        values = {**fixed, **dict(zip(keys, combo))}
        if values == fixed:
            continue
        variants.append({"name": ", ".join(f"{k}={v}" for k, v in zip(keys, combo)), "base": base, "values": values})
    return variants


def cmd_sweep(args: argparse.Namespace) -> int:
    variants = sweep_variants(args.setup, args.base, args.set, args.grid)
    print(f"{len(variants)} variants of {args.setup} template {args.base}", file=sys.stderr)
    sessions = _sessions(args.session)
    if args.local:
        from eyes import backtest

        man = backtest.run(variants=variants, setup=args.setup,
                           sessions=[(s["date"], s["symbol"]) for s in sessions] if sessions else None,
                           progress=lambda i, n: print(f"  {i}/{n}", file=sys.stderr))
        print(json.dumps({k: man[k] for k in ("run_id", "status", "error")}, indent=2))
        return 0 if man["status"] == "done" else 1
    return _post({"setup": args.setup, "variants": variants, "sessions": sessions})


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cmd_list(args: argparse.Namespace) -> int:
    root = backtests_dir(args.dir)
    if not root.is_dir():
        print(f"no runs under {root}")
        return 0
    for folder in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
        man = _read(folder / "manifest.json") or {}
        sessions = man.get("sessions") or []
        print(f"{folder.name}  {man.get('status', '?'):8} templates {[t.get('name') for t in man.get('templates') or []]}"
              f"  sessions {len(sessions)}  setups {sum(int(s.get('setups') or 0) for s in sessions)}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    folder = backtests_dir(args.dir) / args.run_id
    man = _read(folder / "manifest.json")
    if man is None:
        print(f"no run {args.run_id} under {folder.parent}", file=sys.stderr)
        return 1
    print(f"run {man['run_id']}  {man['status']}  {man.get('error') or ''}")
    for s in man.get("sessions") or []:
        rec = s.get("recording") or {}
        print(f"  {s['date']} {s['symbol']:6} {s['status']:7} setups {s.get('setups')}  prints {rec.get('prints')}"
              f"  books {rec.get('books')}  bars {rec.get('bars')} ({rec.get('bars_source')})  {s.get('reason') or ''}")
    summary = _read(folder / "summary.json") or {}
    for tid, t in (summary.get("templates") or {}).items():
        a = t["summary"]["all"]
        by_tape = {k: (v["triggered"], v["avg_net_r"]) for k, v in t["summary"]["by"]["tape_at_trigger"].items()}
        print(f"template {t['name']} ({tid} rev {t['rev']}): armed {a['armed']}  triggered {a['triggered']}"
              f"  win {a['win_pct']}%  avg net R {a['avg_net_r']}  by tape at trigger {by_tape}")
        by_flow = {k: (v["triggered"], v["avg_net_r"])
                   for k, v in (t["summary"]["by"].get("flow_at_trigger") or {}).items()}
        if by_flow:
            print(f"  by flow at trigger {by_flow}")
        if t.get("exits"):
            print(f"  exits {t['exits']}" + (f"  flush {t['flush']}" if t.get("flush") else ""))
        vs = t.get("vs_base")
        if vs and vs["paired"]:
            print(f"  against {vs['base']} on the same {vs['paired']} setups: avg R {vs['avg_r_delta']:+}"
                  f" (better {vs['better']}, worse {vs['worse']}, same {vs['same']})")
        elif vs:
            print(f"  against {vs['base']}: no scored setup in common")
        print(f"  read-out as if live: {t['readout']['state']} -- {t['readout']['reason']}")
    if args.setups and (folder / "setups.jsonl").is_file():
        for line in (folder / "setups.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            print(f"  {r['date']} {r['symbol']:6} {r.get('template_id'):12} {r.get('kind')} trig {r.get('trigger')}"
                  f" stop {r.get('stop')} state {r.get('state')} at-trigger {(r.get('trigger_tape') or {}).get('verdict')}"
                  f" outcome {r.get('outcome')} R {r.get('bar_r')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--template", action="append")
    run.add_argument("--session", action="append", help="DATE:SYMBOL, repeatable; default every usable recording")
    run.add_argument("--local", action="store_true")
    sw = sub.add_parser("sweep")
    sw.add_argument("--setup", default="first_pullback")
    sw.add_argument("--base", default="default", help="the template the variants change")
    sw.add_argument("--grid", action="append", help="KEY=V1,V2,..., repeatable: one variant per combination")
    sw.add_argument("--set", action="append", help="KEY=VALUE, repeatable: on every variant, the base included")
    sw.add_argument("--session", action="append", help="DATE:SYMBOL, repeatable; default every usable recording")
    sw.add_argument("--local", action="store_true")
    lst = sub.add_parser("list")
    lst.add_argument("--dir")
    show = sub.add_parser("show")
    show.add_argument("run_id")
    show.add_argument("--setups", action="store_true")
    show.add_argument("--dir")
    args = ap.parse_args()
    return {"run": cmd_run, "sweep": cmd_sweep, "list": cmd_list, "show": cmd_show}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
