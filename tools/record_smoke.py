"""Prove Session Record captures a live symbol end to end (#315).

    py -3 tools/record_smoke.py SPY --seconds 60

SIDE EFFECTS (explicit, per AGENTS.md invariant #2): this starts a Session
Record for SYMBOL through the running Nova API, polls its health, then stops it.
It refuses to touch a recording that is already running, and it never places an
order. Run it while the market is open (premarket counts) with IB Gateway logged
in; it works on Paper, Live or a Sim desk.

Exit codes: 0 prints reached disk, 1 refused or nothing recorded, 2 Nova API
unreachable.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8000"
POLL_SEC = 5


def verdict(start: dict, samples: list[dict], stopped: dict) -> tuple[bool, list[str]]:
    """Pure: did prints reach disk, and what should the operator know?"""
    notes: list[str] = []
    if start.get("error") or not start.get("capture"):
        return False, [f"Record refused: {start.get('error') or start.get('detail') or 'not started'}"]
    # Same symbol + day resumes one folder, so counts are cumulative: report what
    # THIS run added (counts at stop minus counts right after start).
    before = (start.get("recorder") or {}).get("counts") or {}
    after = (stopped.get("recorder") or {}).get("counts") or {}

    def added(stream: str) -> int:
        return max(0, int(after.get(stream) or 0) - int(before.get(stream) or 0))

    prints, quotes, l2 = added("prints"), added("quotes"), added("l2")
    healthy = [s for s in samples if s.get("healthy")]
    notes.append(f"prints={prints} quotes={quotes} l2={l2} healthy_polls={len(healthy)}/{len(samples)}")
    for sample in samples:
        for key in ("warning", "error"):
            if sample.get(key) and sample[key] not in notes:
                notes.append(sample[key])
    if prints and not (quotes or l2):
        notes.append("Prints only: no depth line was captured, so quotes, Level 2 and print sides did not record")
    return prints > 0, notes


def _call(base: str, method: str, path: str, body: dict | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("NOVA_API_KEY")
    if key:
        headers["X-Nova-Api-Key"] = key
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{base}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read() or b"{}") | {"http_status": exc.code}
        except ValueError:
            return {"error": f"HTTP {exc.code}", "http_status": exc.code}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("symbol")
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--base", default=DEFAULT_BASE)
    args = parser.parse_args(argv)
    symbol = args.symbol.strip().upper()
    try:
        before = _call(args.base, "GET", "/api/capture")
    except (urllib.error.URLError, OSError) as exc:
        print(f"Nova API unreachable at {args.base}: {exc}")
        return 2
    if before.get("capture"):
        print(f"Already recording {before.get('capture_symbol')}; not touching it.")
        return 1
    start = _call(args.base, "POST", "/api/capture", {"enabled": True, "symbol": symbol})
    print("start:", json.dumps({k: start.get(k) for k in ("capture", "capture_symbol", "error", "warning")}))
    samples: list[dict] = []
    if start.get("capture"):
        deadline = time.monotonic() + max(POLL_SEC, args.seconds)
        while time.monotonic() < deadline:
            time.sleep(POLL_SEC)
            status = _call(args.base, "GET", "/api/capture")
            samples.append(status)
            producer = status.get("producer") or {}
            print(f"  +{len(samples) * POLL_SEC:>3}s healthy={status.get('healthy')} "
                  f"producer={producer.get('state')} book={(status.get('book') or {}).get('note') or 'ok'}")
    stopped = _call(args.base, "POST", "/api/capture", {"enabled": False, "symbol": symbol}) if start.get("capture") else {}
    ok, notes = verdict(start, samples, stopped)
    for note in notes:
        print(" -", note)
    print("RESULT:", "RECORDED" if ok else "NOTHING RECORDED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
