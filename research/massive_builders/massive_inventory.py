"""What the Massive flat-file bucket holds and what this plan may read (sizes only). Research tooling.

Credentials: the MASSIVE_S3_* pair from the environment or the .env (massive_env.py; never printed).
Writes <NOVA_EDGE_LAB_DIR>/data/massive_inventory.json.
Usage (repo root): py -3 research/massive_builders/massive_inventory.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import massive_bucket as mf  # noqa: E402
from massive_env import EDGE_LAB  # noqa: E402

BUCKET = mf.BUCKET
OUT = EDGE_LAB / "data" / "massive_inventory.json"


def prefixes(s3, prefix: str) -> list[str]:
    r = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix, Delimiter="/")
    return [p["Prefix"] for p in r.get("CommonPrefixes", [])]


def sizes(s3, prefix: str) -> dict[str, int]:
    out = {}; token = None
    while True:
        kw = {"Bucket": BUCKET, "Prefix": prefix}
        if token:
            kw["ContinuationToken"] = token
        r = s3.list_objects_v2(**kw)
        for o in r.get("Contents", []):
            out[o["Key"]] = int(o["Size"])
        if not r.get("IsTruncated"):
            return out
        token = r.get("NextContinuationToken")


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__); return 0
    s3 = mf.client(max_attempts=6, mode="adaptive")
    top = prefixes(s3, "")
    print("top level:", top)
    inv = {}
    for t in top:
        for ds in prefixes(s3, t):
            years = prefixes(s3, ds)
            inv[ds] = {"years": [y.rstrip("/").rsplit("/", 1)[-1] for y in years]}
            print(f"  {ds}  years {inv[ds]['years'][0] if years else '-'} .. {inv[ds]['years'][-1] if years else '-'}")
    for ds in ("us_stocks_sip/trades_v1/", "us_stocks_sip/minute_aggs_v1/", "us_stocks_sip/day_aggs_v1/", "us_stocks_sip/quotes_v1/"):
        if ds not in inv:
            continue
        by_year = {}
        t0 = time.time()
        for y in inv[ds]["years"]:
            s = sizes(s3, f"{ds}{y}/")
            by_year[y] = {"files": len(s), "gb": round(sum(s.values()) / 2**30, 2)}
        inv[ds]["by_year"] = by_year
        print(f"\n{ds} ({time.time() - t0:.0f}s)")
        for y, v in by_year.items():
            print(f"   {y}: {v['files']:4d} files, {v['gb']:9.2f} GB")
        print(f"   total {sum(v['gb'] for v in by_year.values()):,.1f} GB")
    OUT.write_text(json.dumps(inv, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
