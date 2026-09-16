"""Advise worker process entry. Isolated from the IBKR/API event loop.

Usage:
  python -m advise.worker_main --run-id 12
  nova-api.exe --advise-worker --run-id 12
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback

from dotenv import load_dotenv

from advise.book import append_event, get_run, set_result, set_usage, update_status
from advise.engine import run_debate
from advise.events import encode_event, make_event
from advise.usage import empty_usage, should_persist
from paths import env_file_path


def _persist_usage(run_id: int, usage: dict) -> None:
    if not should_persist(usage):
        return
    set_usage(
        run_id,
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        actual_usd=usage.get("actual_usd"),
    )


def _emit_stdout(event: dict) -> None:
    sys.stdout.write(encode_event(event) + "\n")
    sys.stdout.flush()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="advise-worker")
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--advise-worker", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(env_file_path())
    args = parse_args(argv)
    run = get_run(int(args.run_id))
    if run is None:
        _emit_stdout(make_event("error", message=f"run {args.run_id} not found"))
        return 2
    update_status(run["id"], "running")
    symbol = run["symbol"]
    depth = int(run["depth"])

    def emit(event: dict) -> None:
        append_event(run["id"], event)
        _emit_stdout(event)

    usage = empty_usage()
    try:
        result = run_debate(symbol, depth, emit, usage_out=usage)
        set_result(run["id"], result)
        _persist_usage(run["id"], usage)
        update_status(run["id"], "complete", finished=True)
        _emit_stdout(make_event("done", status="complete"))
        return 0
    except KeyboardInterrupt:
        _persist_usage(run["id"], usage)
        update_status(run["id"], "cancelled", fail_reason="cancelled", finished=True)
        _emit_stdout(make_event("error", message="cancelled"))
        return 130
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        event = make_event("error", message=reason)
        try:
            append_event(run["id"], event)
        except Exception:
            pass
        _persist_usage(run["id"], usage)
        update_status(run["id"], "failed", fail_reason=reason, finished=True)
        _emit_stdout(event)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8:backslashreplace")
    raise SystemExit(main())
