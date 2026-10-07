"""Talk to Nova's agent endpoints (ADR 050) from an agent session: find stock-days, show them in the Sim.

Reads the desk's API key from the environment (``NOVA_API_KEY``) or from the operator's ``.env`` (``NOVA_ENV_PATH``,
else the main checkout's -- a worktree has none) and never prints it. Talks to ``NOVA_API_BASE`` (default
``http://127.0.0.1:8000``). Percentages are percent points (300 = +300%). Nothing here places an order.

Usage (from the repo root):
    py -3 tools/nova_agent.py status                                   # the endpoints, the index, the desk
    py -3 tools/nova_agent.py find --high-min 300 --price-max 20       # stock-days; any /api/agent/movers argument
    py -3 tools/nova_agent.py find --set close_pos_min=0.67 --set high_after=09:30
    py -3 tools/nova_agent.py row 2026-09-25 MSGY                      # one stock-day as the index holds it
    py -3 tools/nova_agent.py show MSGY 2026-09-25 [--at run|high|09:45] [--confirm]
    py -3 tools/nova_agent.py move --to high | --by -5 | --pause | --play
    py -3 tools/nova_agent.py desk                                     # what the desk shows now
    py -3 tools/nova_agent.py dict [list|match WORDS|add FILE.json|remove ID]
    py -3 tools/nova_agent.py cmd ID [--wait 20]
    add --json to any command for the raw answer.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
API = os.environ.get("NOVA_API_BASE", "http://127.0.0.1:8000").rstrip("/")
KEY_HEADER = "X-Nova-Api-Key"
FOLLOW_SEC = 15 * 60


# ── The key and the requests ────────────────────────────────────────────────

def _main_checkout() -> Path:
    """The main checkout (where the operator's .env lives), also from a worktree."""
    try:
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=REPO,
                                capture_output=True, text=True, check=True).stdout.strip()
        return Path(common).parent
    except (OSError, subprocess.CalledProcessError):
        return REPO


def _env_key(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.strip().partition("=")
            if sep and name.strip() == "NOVA_API_KEY":
                return value.strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def api_key() -> str:
    if os.environ.get("NOVA_API_KEY", "").strip():
        return os.environ["NOVA_API_KEY"].strip()
    candidates = [Path(os.environ["NOVA_ENV_PATH"])] if os.environ.get("NOVA_ENV_PATH") else []
    candidates += [_main_checkout() / ".env", REPO / ".env"]
    for path in candidates:
        if key := _env_key(path):
            return key
    return ""


class NovaError(RuntimeError):
    def __init__(self, status: int, detail: Any) -> None:
        self.status, self.detail = status, detail
        reason = detail.get("reason") if isinstance(detail, dict) else None
        error = detail.get("error") if isinstance(detail, dict) else detail
        super().__init__(f"{status} {reason or ''} {error}".strip())


def call(method: str, path: str, *, params: dict | None = None, body: dict | None = None, timeout: float = 40) -> Any:
    url = f"{API}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    if key := api_key():
        request.add_header(KEY_HEADER, key)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode() or "null")
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode()).get("detail")
        except (ValueError, AttributeError):
            detail = exc.reason
        raise NovaError(exc.code, detail) from None
    except urllib.error.URLError as exc:
        raise SystemExit(f"Nova's backend does not answer at {API}: {exc.reason}") from None


# ── Output ──────────────────────────────────────────────────────────────────

def _fmt_pct(value: Any) -> str:
    return "" if value is None else f"{value:+.0f}%"


def _fmt_num(value: Any) -> str:
    if value is None:
        return ""
    value = float(value)
    for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= div:
            return f"{value / div:.1f}{suffix}"
    return f"{value:g}"


def print_movers(answer: dict) -> None:
    rows = answer.get("rows") or []
    print(f"{answer.get('count')} matched (showing {len(rows)})  query: {answer.get('query')}")
    if answer.get("too_broad"):
        print("too broad to list:", "; ".join(answer.get("notes") or []))
        return
    print(f"{'#':>2}  {'date':10}  {'symbol':6}  {'prior':>7}  {'high':>7}  {'high%':>7}  {'at':>5}  "
          f"{'close%':>7}  {'gap%':>6}  {'pos':>4}  {'volume':>7}  {'$vol':>7}  notes")
    for i, r in enumerate(rows, 1):
        notes = [n for n in (r.get("split") and f"split:{r['split']}", None if r.get("replayable") is not False
                             else "no ticks", r.get("float") and f"float:{r['float']['proof']}") if n]
        pos = "" if r["close_pos"] is None else f"{r['close_pos']:.2f}"
        print(f"{i:>2}  {r['date']:10}  {r['symbol']:6}  {r['prev_close'] or 0:>7.3g}  {r['day_high'] or 0:>7.3g}  "
              f"{_fmt_pct(r['high_pct']):>7}  {r.get('day_high_et') or '':>5}  {_fmt_pct(r['close_pct']):>7}  "
              f"{_fmt_pct(r['gap_pct']):>6}  {pos:>4}  "
              f"{_fmt_num(r['volume']):>7}  {_fmt_num(r['dollar_volume']):>7}  {' '.join(notes)}")
    summary = answer.get("summary") or {}
    if summary:
        print("summary:", ", ".join(f"{k} {v}" for k, v in summary.items() if v is not None))
    for note in answer.get("notes") or []:
        print("note:", note)
    cov = answer.get("coverage") or {}
    if cov:
        print(f"index: {cov.get('sessions')} sessions {cov.get('first')}..{cov.get('last')}; "
              f"{cov.get('missing')} days on disk not built yet")


def follow(command: dict, wait_total: float = FOLLOW_SEC, as_json: bool = False) -> dict:
    """Follow a command until it finishes, printing each new step."""
    seen = None
    deadline = time.time() + wait_total
    while True:
        status, text = command["status"], (command.get("steps") or [{}])[-1].get("text")
        if not as_json and (status, text) != seen:
            print(f"[{status}] {text or command.get('step') or ''}".rstrip(), flush=True)
            seen = (status, text)
        if status not in ("queued", "running") or time.time() > deadline:
            return command
        command = call("GET", f"/api/agent/commands/{command['id']}", params={"wait": 20}, timeout=40)["command"]


# ── Commands ────────────────────────────────────────────────────────────────

def _movers_params(args) -> dict:
    params = {name: getattr(args, name) for name in ("high_min", "high_max", "low_max", "close_min", "close_max",
                                                     "gap_min", "price_min", "price_max", "float_max", "symbol",
                                                     "sort", "limit") if getattr(args, name) is not None}
    if args.date_from:
        params["from"] = args.date_from
    if args.date_to:
        params["to"] = args.date_to
    if args.replayable:
        params["replayable"] = "true"
    for pair in args.set or []:
        name, _, value = pair.partition("=")
        params[name.strip()] = value.strip()
    return params


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json", action="store_true", help="print the raw answer")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("desk")
    find = sub.add_parser("find")
    for name in ("high-min", "high-max", "low-max", "close-min", "close-max", "gap-min", "price-min", "price-max",
                 "float-max"):
        find.add_argument(f"--{name}", type=float)
    find.add_argument("--symbol")
    find.add_argument("--from", dest="date_from")
    find.add_argument("--to", dest="date_to")
    find.add_argument("--sort")
    find.add_argument("--limit", type=int)
    find.add_argument("--replayable", action="store_true")
    find.add_argument("--set", action="append", help="any other search argument, name=value")
    row = sub.add_parser("row")
    row.add_argument("date")
    row.add_argument("symbol")
    show = sub.add_parser("show")
    show.add_argument("symbol")
    show.add_argument("date")
    show.add_argument("--at")
    show.add_argument("--confirm", action="store_true", help="only after the operator agreed to what is at stake")
    show.add_argument("--no-wait", action="store_true")
    move = sub.add_parser("move")
    move.add_argument("--to")
    move.add_argument("--by", type=float, dest="by_min")
    move.add_argument("--pause", action="store_true")
    move.add_argument("--play", action="store_true")
    move.add_argument("--confirm", action="store_true")
    words = sub.add_parser("dict")
    words.add_argument("action", nargs="?", default="list", choices=("list", "match", "add", "remove"))
    words.add_argument("arg", nargs="*")
    cmd = sub.add_parser("cmd")
    cmd.add_argument("id")
    cmd.add_argument("--wait", type=float, default=0)
    args = ap.parse_args(argv)

    def out(value: Any) -> None:
        print(json.dumps(value, indent=2))

    try:
        if args.cmd == "status":
            answer = call("GET", "/api/agent")
            if args.json:
                out(answer)
            else:
                idx, desk = answer["index"], answer["desk"]
                print(f"index: {'ok' if idx['ok'] else idx['error']}; {idx['sessions']} sessions "
                      f"{idx['first']}..{idx['last']}; {idx['rows']:,} rows; on disk through {idx['files_last']}; "
                      f"{idx['missing']} days not built")
                print(f"desk: {'listening' if desk['listening'] else 'NOT listening (open the desk)'}; "
                      f"dictionary: {answer['dictionary']['entries']} entries")
                for rule in answer["rules"]:
                    print("rule:", rule)
        elif args.cmd == "desk":
            out(call("GET", "/api/agent/desk"))
        elif args.cmd == "find":
            answer = call("GET", "/api/agent/movers", params={k.replace("-", "_"): v for k, v in
                                                               _movers_params(args).items()}, timeout=120)
            out(answer) if args.json else print_movers(answer)
        elif args.cmd == "row":
            out(call("GET", f"/api/agent/movers/{args.date}/{args.symbol.upper()}"))
        elif args.cmd == "show":
            body = {"symbol": args.symbol, "date": args.date, "confirm": args.confirm}
            if args.at:
                body["at"] = args.at
            command = call("POST", "/api/agent/show", body=body)["command"]
            plan = command["plan"]
            if not args.json:
                print(f"showing {plan['symbol']} {plan['date']}: park {plan['park_et']} ET ({plan['at']}), window "
                      f"{plan['window']['start']}-{plan['window']['end']}"
                      + ("; the desk moves to the Sim" if plan.get("switch_venue") else ""))
            final = command if args.no_wait else follow(command, as_json=args.json)
            if args.json:
                out(final)
            return 0 if final["status"] in ("done", "queued", "running") else 1
        elif args.cmd == "move":
            body: dict[str, Any] = {"confirm": args.confirm}
            if args.to:
                body["to"] = args.to
            if args.by_min is not None:
                body["by_min"] = args.by_min
            if args.pause or args.play:
                body["paused"] = bool(args.pause)
            final = follow(call("POST", "/api/agent/move", body=body)["command"], as_json=args.json)
            if args.json:
                out(final)
            return 0 if final["status"] == "done" else 1
        elif args.cmd == "dict":
            if args.action == "add":
                entry = json.loads(Path(args.arg[0]).read_text(encoding="utf-8"))
                out(call("POST", "/api/agent/dictionary", body={"entry": entry})["entry"])
            elif args.action == "remove":
                call("DELETE", f"/api/agent/dictionary/{args.arg[0]}")
                print(f"removed {args.arg[0]}")
            else:
                answer = call("GET", "/api/agent/dictionary")
                words_in = " ".join(args.arg).lower()
                entries = [e for e in answer["entries"] if args.action == "list"
                           or any(w in " ".join(e.get("phrases", [])).lower() for w in words_in.split())]
                if args.json:
                    out(entries)
                else:
                    if answer.get("error"):
                        print("dictionary error:", answer["error"])
                    for e in entries:
                        print(f"- {e['id']}{' (seed)' if e.get('seed') else ''}: {e['means']}")
                        print(f"    says: {' | '.join(e['phrases'])}")
                        print(f"    call: {e['call']['method']} {e['call']['path']} "
                              f"{json.dumps(e['call'].get('params') or e['call'].get('body') or {})}")
        elif args.cmd == "cmd":
            out(call("GET", f"/api/agent/commands/{args.id}", params={"wait": args.wait}, timeout=args.wait + 15))
    except NovaError as exc:
        print(f"Nova refused: {exc}", file=sys.stderr)
        if isinstance(exc.detail, dict) and exc.detail.get("at_stake"):
            for item in exc.detail["at_stake"].get("items", []):
                print(f"  at stake: {item['text']}", file=sys.stderr)
            for item in exc.detail["at_stake"].get("unknown", []):
                print(f"  could not check: {item['kind']} ({item['error']})", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
