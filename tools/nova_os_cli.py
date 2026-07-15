"""Thin read-only Nova OS CLI — HTTP client only; never places orders.

Usage (from repo root, with API running):
  py tools/nova_os_cli.py policy
  py tools/nova_os_cli.py events [--limit N] [--symbol XYZ]
  py tools/nova_os_cli.py decide [SYMBOL] [--limit N]
  py tools/nova_os_cli.py decide --limit 4 --json
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = "http://127.0.0.1:8000"


def _get(base: str, path: str, params: dict | None = None) -> dict | list:
    qs = f"?{urllib.parse.urlencode(params)}" if params else ""
    url = f"{base.rstrip('/')}{path}{qs}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} {url}\n{body}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Cannot reach Nova API at {base}: {exc.reason}") from exc


def _print(data: object, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2))
        return
    if isinstance(data, dict) and "decision" in data:
        d = data
        print(f"{d.get('symbol')} → {d.get('decision')}  mode={d.get('mode')}  conf={d.get('confidence')}")
        print(f"  reasons: {', '.join(d.get('reason_codes') or [])}")
        failed = next((g for g in d.get('gates') or [] if not g.get('passed')), None)
        if failed:
            print(f"  first fail: {failed.get('name')} ({', '.join(failed.get('reason_codes') or [])})")
        ticket = d.get("ticket")
        if ticket:
            print(
                f"  ticket: entry={ticket.get('entry')} stop={ticket.get('stop')} "
                f"target={ticket.get('target')} shares={ticket.get('shares')}"
            )
        print(f"  would_execute={d.get('would_execute')} executed={d.get('executed')}")
        return
    if isinstance(data, dict) and "decisions" in data:
        for row in data["decisions"]:
            _print(row, False)
            print()
        return
    if isinstance(data, dict) and "events" in data:
        for ev in data["events"]:
            print(
                f"#{ev.get('id')} {ev.get('kind')} {ev.get('symbol')} "
                f"{ev.get('decision')}/{ev.get('action')} reasons={ev.get('reason_codes')}"
            )
        return
    print(json.dumps(data, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Nova OS read-only CLI (policy / events / decide). Never places orders.",
    )
    parser.add_argument("--base", default=DEFAULT_BASE, help="API base URL")
    parser.add_argument("--json", action="store_true", help="Raw JSON output")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("policy", help="Show policy version + vocabulary")

    p_events = sub.add_parser("events", help="Recent audit receipts")
    p_events.add_argument("--limit", type=int, default=20)
    p_events.add_argument("--symbol", default=None)

    p_decide = sub.add_parser("decide", help="Run decide for symbol or top watchlist")
    p_decide.add_argument("symbol", nargs="?", default=None)
    p_decide.add_argument("--limit", type=int, default=4)

    args = parser.parse_args()
    if args.cmd == "policy":
        _print(_get(args.base, "/api/nova-os/policy"), args.json)
    elif args.cmd == "events":
        params: dict = {"limit": args.limit}
        if args.symbol:
            params["symbol"] = args.symbol.upper()
        _print(_get(args.base, "/api/nova-os/events", params), args.json)
    elif args.cmd == "decide":
        if args.symbol:
            _print(_get(args.base, f"/api/nova-os/decide/{args.symbol.upper()}"), args.json)
        else:
            _print(_get(args.base, "/api/nova-os/decide", {"limit": args.limit}), args.json)
    else:
        parser.error(f"unknown command {args.cmd}")


if __name__ == "__main__":
    main()
