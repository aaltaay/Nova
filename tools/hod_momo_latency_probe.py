"""CLI: sample active-set quote/eval ages for live acceptance gates.

Usage (API running, IB Gateway connected)::

    py -3 tools/hod_momo_latency_probe.py
    py -3 tools/hod_momo_latency_probe.py --seconds 60 --interval 2

Exit codes: 0 = gates pass, 1 = warn/incomplete, 2 = fail/unreachable.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8000"


def _fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Nova HOD active-set latency probe")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    endpoint = args.url.rstrip("/") + "/api/integrity"
    samples: list[dict] = []
    deadline = time.time() + max(1.0, args.seconds)
    try:
        while time.time() < deadline:
            payload = _fetch(endpoint)
            metrics = ((payload.get("hod") or {}).get("metrics")) or payload.get("metrics") or {}
            samples.append({
                "ts": time.time(),
                "status": payload.get("status"),
                "active_set_size": metrics.get("active_set_size"),
                "uncovered_count": metrics.get("uncovered_count"),
                "active_coverage_pct": metrics.get("active_coverage_pct"),
                "active_quote_age_p95": metrics.get("active_quote_age_p95"),
                "active_quote_age_max": metrics.get("active_quote_age_max"),
                "active_eval_age_p95": metrics.get("active_eval_age_p95"),
                "active_eval_age_max": metrics.get("active_eval_age_max"),
            })
            time.sleep(max(0.5, args.interval))
    except urllib.error.URLError as exc:
        print(f"PROBE UNREACHABLE: {endpoint} ({exc})", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"PROBE ERROR: {exc}", file=sys.stderr)
        return 2

    def _vals(key: str) -> list[float]:
        out = []
        for s in samples:
            v = s.get(key)
            if v is not None:
                out.append(float(v))
        return out

    quote_p95 = _vals("active_quote_age_p95")
    quote_max = _vals("active_quote_age_max")
    eval_p95 = _vals("active_eval_age_p95")
    eval_max = _vals("active_eval_age_max")
    cov = _vals("active_coverage_pct")

    summary = {
        "samples": len(samples),
        "quote_p95_median": statistics.median(quote_p95) if quote_p95 else None,
        "quote_max_median": statistics.median(quote_max) if quote_max else None,
        "eval_p95_median": statistics.median(eval_p95) if eval_p95 else None,
        "eval_max_median": statistics.median(eval_max) if eval_max else None,
        "coverage_median": statistics.median(cov) if cov else None,
        "last": samples[-1] if samples else None,
    }
    if args.json:
        print(json.dumps({"summary": summary, "samples": samples}, indent=2))
    else:
        print(
            "probe samples={samples} quote_p95~{qp} quote_max~{qm} "
            "eval_p95~{ep} eval_max~{em} coverage~{cv}".format(
                samples=summary["samples"],
                qp=summary["quote_p95_median"],
                qm=summary["quote_max_median"],
                ep=summary["eval_p95_median"],
                em=summary["eval_max_median"],
                cv=summary["coverage_median"],
            )
        )

    # Gates: p95<=2, max<=3, coverage 100
    qp = summary["quote_p95_median"]
    qm = summary["quote_max_median"]
    ep = summary["eval_p95_median"]
    em = summary["eval_max_median"]
    cv = summary["coverage_median"]
    if None in (qp, qm, ep, em, cv):
        print("PROBE INCOMPLETE: missing age/coverage samples", file=sys.stderr)
        return 1
    if qp <= 2.0 and qm <= 3.0 and ep <= 2.0 and em <= 3.0 and cv >= 100.0:
        return 0
    print("PROBE FAIL: active-set freshness/coverage gates not met", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
