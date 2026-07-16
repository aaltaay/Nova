"""CLI: fail loud if HOD / scanner data-flow integrity is not pass.

Usage (API running)::

    py -3 tools/hod_momo_integrity_check.py
    py -3 tools/hod_momo_integrity_check.py --url http://127.0.0.1:8000

Exit codes: 0 = pass, 1 = warn, 2 = fail/unreachable.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8000"


def main() -> int:
    parser = argparse.ArgumentParser(description="Nova HOD/scanner integrity check")
    parser.add_argument("--url", default=DEFAULT_URL, help="API base URL")
    parser.add_argument("--json", action="store_true", help="print full JSON report")
    args = parser.parse_args()
    endpoint = args.url.rstrip("/") + "/api/integrity"
    try:
        with urllib.request.urlopen(endpoint, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        print(f"INTEGRITY UNREACHABLE: {endpoint} ({exc})", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"INTEGRITY ERROR: {exc}", file=sys.stderr)
        return 2

    status = (payload.get("status") or "fail").lower()
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"status={status} ok={payload.get('ok')}")
        for part, st in (payload.get("parts") or {}).items():
            print(f"  {part}: {st}")
        for c in payload.get("checks") or []:
            if c.get("status") != "pass":
                print(f"  [{c.get('status')}] {c.get('id')}: {c.get('detail')}")

    if status == "pass":
        return 0
    if status == "warn":
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
