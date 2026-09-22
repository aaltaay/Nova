"""Gate 1 runner for Gap and Go: wait for the pre-market pass and the reference dump, then
load news + ticker details, build both selections (with and without the float pillar),
extract the minute bars once for their union, and run the base + grid. One log.

Usage:
    py -3 run_gate1_gng.py --wait-pid 4868 --wait-marker "F:\\Nova\\data\\massive\\store\\reference\\dump.log"
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(*args: str) -> None:
    print(f"\n$ {' '.join(args)}", flush=True)
    t0 = time.time()
    subprocess.run([sys.executable, *args], check=True)
    print(f"  ({time.time() - t0:.0f}s)", flush=True)


def pid_alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
    return str(pid) in out


def marker_present(path: Path, marker: bytes) -> bool:
    return path.exists() and marker in path.read_bytes().replace(b"\x00", b"")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait-pid", type=int, default=0)
    ap.add_argument("--wait-marker", default="")
    ap.add_argument("--marker", default="=== dump complete")
    a = ap.parse_args()
    while (a.wait_pid and pid_alive(a.wait_pid)) or (a.wait_marker and not marker_present(Path(a.wait_marker), a.marker.encode())):
        time.sleep(30)
    print("prerequisites met; starting Gap and Go gate 1", flush=True)

    sys.path.insert(0, str(HERE))
    from common import connect  # noqa: E402

    run(str(HERE / "build_news.py"))
    run(str(HERE / "select_gng.py"), "--top", "20")
    run(str(HERE / "select_gng.py"), "--top", "20", "--no-float", "--table", "gng_selection_nofloat")
    con = connect()
    con.execute("CREATE OR REPLACE VIEW gng_union AS "
                "SELECT ticker, d FROM gng_selection UNION SELECT ticker, d FROM gng_selection_nofloat")
    n = con.execute("SELECT count(*), count(DISTINCT d) FROM gng_union").fetchone()
    print(f"gng_union: {n[0]} symbol-days over {n[1]} days", flush=True)
    con.close()
    run(str(HERE / "extract_minutes.py"), "--selection", "gng_union", "--table", "minutes_gng")
    run(str(HERE / "backtest_gng.py"), "--tag", "gng_base")
    run(str(HERE / "backtest_gng.py"), "--grid", "--tag", "gng")
    print("=== gng gate1 complete ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
