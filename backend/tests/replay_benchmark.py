"""Opt-in offline replay benchmark; no Gateway or operator archive is touched.

Run from the repository root: py -3 backend/tests/replay_benchmark.py LABEL
The fixed .tmp/replay-bench fixture and LABEL.json are disposable. Run this same
harness on each revision; timing includes TestClient overhead, not a TCP server.
"""

# ruff: noqa: E402 -- fixture environment must precede backend imports.
import argparse
import concurrent.futures
import gc
import json
import math
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("label", nargs="?", default="before")
parser.add_argument("--directory", type=Path, default=ROOT / ".tmp" / "replay-bench")
args = parser.parse_args()
SCRATCH = args.directory.resolve()
os.environ["NOVA_SIM_HISTORY_DIR"] = str(SCRATCH / "history")
import psutil
from archive import db
from sim import history_store as store, history_playback as playback, session_clock as clock, mode
from sim.history_routes import router
from fastapi import FastAPI
from fastapi.testclient import TestClient

db.cache_dir = lambda: SCRATCH / "bars"
db.cache_dir().mkdir(parents=True, exist_ok=True)
db.init_db()
spec = store.window("BENCH", "2026-09-18", "04:00", "09:30")
a, b = spec["start_ts"], spec["end_ts"]
job = store.create(spec, "trades")
if not job["count"]:
    # 20% unreported; every 396th second starts with a 400-print burst.
    stamps = [a + (i * (b - a) // 230000) for i in range(230000)]
    stamps += [a + second for second in range(0, 19800, 396) for _ in range(400)]
    stamps.sort()
    rows = [
        dict(
            ts=ts,
            price=10 + (i % 91) / 100,
            size=1 + i % 300,
            symbol="BENCH",
            exchange="TEST",
            conditions="",
            unreported=i % 5 == 0,
        )
        for i, ts in enumerate(stamps)
    ]
    store.commit_page(job["id"], a, rows, b, True)
    bars_job = store.create(spec, "bars")
    bars = [
        dict(t=datetime.fromtimestamp(a + i * 60, timezone.utc).isoformat(), o=10, h=11, l=10, c=10.5, v=5000)
        for i in range(330)
    ]
    store.save_candles(bars_job["id"], bars)
    store.update(bars_job["id"], status="complete", cursor=b, count=len(bars))
    del rows, bars, stamps
clock.reset_for_tests()
playback.clear()
mode.is_sim_mode = lambda: True
app = FastAPI()
app.include_router(router)
client = TestClient(app)
gc.collect()
proc = psutil.Process()
rss = proc.memory_info().rss
t = time.perf_counter()
selected = client.post("/api/sim/history/select", json={k: spec[k] for k in ("symbol", "date", "start", "end")})
assert selected.status_code == 200, selected.text
select_ms = (time.perf_counter() - t) * 1000
clock.set_paused(True)
gc.collect()
out = dict(
    python=platform.python_version(),
    platform=platform.platform(),
    prints=250000,
    unreported=50000,
    candles=330,
    samples=40,
    select_ms=select_ms,
    select_rss_delta_mib=(proc.memory_info().rss - rss) / 1048576,
    playheads={},
)


def percentiles(values):
    values = sorted(values)
    return dict(p50_ms=values[len(values) // 2], p95_ms=values[math.ceil(0.95 * len(values)) - 1], max_ms=max(values))


def snapshot():
    response = client.get("/api/sim/history/snapshot/BENCH")
    assert response.status_code == 200
    return response.json()


def bars():
    return playback.bars("BENCH", "1Min", 2000, clock.now_et())


for name, second in [("early", 60), ("mid", 9900), ("late", 19800)]:
    clock.scrub_to_second(second)
    result = {}
    for key, fn in [("snapshot_http", snapshot), ("bars", bars)]:
        t = time.perf_counter()
        fn()
        result[key + "_cold_ms"] = (time.perf_counter() - t) * 1000
        samples = []
        for _ in range(40):
            t = time.perf_counter()
            fn()
            samples.append((time.perf_counter() - t) * 1000)
        result[key] = percentiles(samples)

    def loop(_):
        samples = []
        for _ in range(20):
            t = time.perf_counter()
            snapshot()
            bars()
            samples.append((time.perf_counter() - t) * 1000)
        return samples

    t = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        samples = sum(executor.map(loop, range(4)), [])
    result["concurrent_4_snapshot_bars"] = dict(percentiles(samples), wall_ms=(time.perf_counter() - t) * 1000)
    out["playheads"][name] = result
out["warm_rss_delta_mib"] = (proc.memory_info().rss - rss) / 1048576
label = args.label
(SCRATCH / (label + ".json")).write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps(out, indent=2))
