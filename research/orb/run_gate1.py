"""Gate 1 runner: wait for the extraction to finish, fold in the September top-up days,
reselect, re-extract the days whose lookback changed, then run the base backtest and the
robustness pass. One log, no round trips.

Usage:
    py -3 run_gate1.py --wait-pid 44736
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = [sys.executable, "-3"] if Path(sys.executable).name.lower() == "py.exe" else [sys.executable]


def run(*args: str) -> None:
    print(f"\n$ {' '.join(args)}", flush=True)
    t0 = time.time()
    subprocess.run([*PY, *args], check=True)
    print(f"  ({time.time() - t0:.0f}s)", flush=True)


def pid_alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
    return str(pid) in out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait-pid", type=int, default=0)
    ap.add_argument("--reextract-before", default="2021-11-05")
    a = ap.parse_args()
    while a.wait_pid and pid_alive(a.wait_pid):
        time.sleep(15)
    print("extraction runner gone; starting gate 1", flush=True)

    sys.path.insert(0, str(HERE))
    from common import connect  # noqa: E402

    run(str(HERE / "build_store.py"))                      # builds the 8 September top-up days
    run(str(HERE / "build_store.py"), "--no-build", "--select", "--top", "30")
    con = connect()
    n = con.execute("DELETE FROM extracted_days WHERE d < ?::DATE", [a.reextract_before]).fetchone()
    con.execute("DELETE FROM minutes_selected WHERE d < ?::DATE", [a.reextract_before])
    print(f"re-extracting days before {a.reextract_before}: {n}", flush=True)
    con.close()
    run(str(HERE / "extract_minutes.py"))
    run(str(HERE / "backtest_orb.py"), "--top", "20", "--tag", "base")
    run(str(HERE / "robustness.py"), "--tag", "base")
    print("=== gate1 complete ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
