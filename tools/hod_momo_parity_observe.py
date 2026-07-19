"""Observe Warrior HOD Momentum vs Nova HOD Momo alerts (research-only).

Never feeds Warrior symbols into Nova's alert engine. Writes gitignored
artifacts under ``.tmp/hod-momo-parity/``.

Usage::

    py -3 tools/hod_momo_parity_observe.py --once
    py -3 tools/hod_momo_parity_observe.py --interval 20

Refuse to arm if session gate exits 2 (integrity fail).
Exit 3 = BLOCKED (session gate / API).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / ".tmp" / "hod-momo-parity"
DEFAULT_URL = "http://127.0.0.1:8000"
SENTINEL = "AGENT_LOOP_TICK_hod_parity"


def _fetch(url: str) -> dict | list:
    # Match session_gate: busy IBKR event loops routinely exceed 10s on /alerts + /integrity.
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _normalize_strategy(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def _alert_unix(a: dict) -> float:
    ts = a.get("created_ts")
    if isinstance(ts, (int, float)) and ts > 0:
        return float(ts)
    raw = a.get("timestamp")
    if isinstance(raw, str) and raw:
        try:
            # Support Zulu ISO
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def _nova_rows(base: str, *, recent_sec: float = 1800.0, limit: int = 400) -> list[dict]:
    """Nova alerts from the recent window only (not the entire day dump)."""
    # Cap payload — full-day dumps (9k+) stall the observe loop.
    payload = _fetch(
        base.rstrip("/") + f"/api/hod-momo/alerts?limit={max(50, int(limit))}"
    )
    alerts = payload if isinstance(payload, list) else payload.get("alerts") or []
    cutoff = time.time() - max(60.0, recent_sec)
    rows = []
    for a in alerts:
        unix = _alert_unix(a)
        if unix and unix < cutoff:
            continue
        rows.append({
            "symbol": (a.get("ticker") or a.get("symbol") or "").strip().upper(),
            "strategy": _normalize_strategy(a.get("strategy_name") or ""),
            "strategy_id": a.get("strategy_id"),
            "ts": unix or a.get("timestamp"),
            "source": "nova",
        })
    return [r for r in rows if r["symbol"]]


def _load_warrior_snapshot() -> list[dict]:
    """Load optional Warrior DOM extract written by the warrior agent."""
    path = OUT_DIR / "warrior_latest.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data if isinstance(data, list) else data.get("rows") or []
    out = []
    for r in rows:
        sym = (r.get("symbol") or "").strip().upper()
        if not sym:
            continue
        out.append({
            "symbol": sym,
            "strategy": _normalize_strategy(r.get("strategy") or r.get("strategy_name") or ""),
            "ts": r.get("ts") or r.get("time"),
            "source": "warrior",
        })
    return out


def _diff(warrior: list[dict], nova: list[dict], window_sec: float = 60.0) -> dict:
    def key(r: dict) -> tuple[str, str]:
        return (r["symbol"], r.get("strategy") or "")

    w_keys = {key(r) for r in warrior}
    n_keys = {key(r) for r in nova}
    both = sorted(w_keys & n_keys)
    warrior_only = sorted(w_keys - n_keys)
    nova_only = sorted(n_keys - w_keys)
    # Strategy mismatch: same symbol, different strategy sets
    w_by_sym: dict[str, set[str]] = {}
    n_by_sym: dict[str, set[str]] = {}
    for r in warrior:
        w_by_sym.setdefault(r["symbol"], set()).add(r.get("strategy") or "")
    for r in nova:
        n_by_sym.setdefault(r["symbol"], set()).add(r.get("strategy") or "")
    mismatch = sorted(
        s for s in (set(w_by_sym) & set(n_by_sym))
        if w_by_sym[s] != n_by_sym[s]
    )
    return {
        "window_sec": window_sec,
        "both": [{"symbol": s, "strategy": st} for s, st in both],
        "warrior_only": [{"symbol": s, "strategy": st} for s, st in warrior_only],
        "nova_only": [{"symbol": s, "strategy": st} for s, st in nova_only],
        "strategy_mismatch_symbols": mismatch,
        "counts": {
            "warrior": len(warrior),
            "nova": len(nova),
            "both": len(both),
            "warrior_only": len(warrior_only),
            "nova_only": len(nova_only),
        },
    }


def _session_gate(url: str) -> int:
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "hod_momo_session_gate.py"),
        "--url", url,
        "--profile", "integrity_only",
    ]
    return subprocess.call(cmd, cwd=str(ROOT))


def _write_artifacts(nova: list[dict], diff: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "nova_latest.json").write_text(
        json.dumps({"ts": time.time(), "rows": nova}, indent=2),
        encoding="utf-8",
    )
    (OUT_DIR / "diff_latest.json").write_text(
        json.dumps(diff, indent=2),
        encoding="utf-8",
    )
    summary = [
        f"# HOD parity snapshot {datetime.now(timezone.utc).isoformat()}",
        "",
        f"- warrior rows: {diff['counts']['warrior']}",
        f"- nova rows: {diff['counts']['nova']}",
        f"- both: {diff['counts']['both']}",
        f"- warrior_only: {diff['counts']['warrior_only']}",
        f"- nova_only: {diff['counts']['nova_only']}",
        "",
    ]
    if diff["warrior_only"]:
        summary.append("## warrior_only")
        for r in diff["warrior_only"][:40]:
            summary.append(f"- {r['symbol']} | {r['strategy'] or '(any)'}")
        summary.append("")
    (OUT_DIR / "summary.md").write_text("\n".join(summary), encoding="utf-8")
    events_path = OUT_DIR / "events.jsonl"
    if diff["warrior_only"]:
        event = {
            "ts": time.time(),
            "type": "warrior_only",
            "rows": diff["warrior_only"],
        }
        with events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
        print(
            f"{SENTINEL} "
            + json.dumps({
                "prompt": "Classify new warrior_only HOD rows vs Nova /debug/symbol",
                "count": len(diff["warrior_only"]),
            })
        )


def run_once(url: str, *, require_gate: bool = True) -> int:
    if require_gate:
        gate = _session_gate(url)
        if gate == 3:
            print("PARITY OBSERVE BLOCKED: session gate blocked", file=sys.stderr)
            return 3
        if gate == 2:
            print(
                "PARITY OBSERVE REFUSED: integrity fail (session_gate exit=2) — "
                "fix Nova feed before comparing to Warrior",
                file=sys.stderr,
            )
            return 2
    try:
        nova = _nova_rows(url)
    except Exception as exc:
        print(f"PARITY OBSERVE BLOCKED: Nova alerts fetch failed ({exc})", file=sys.stderr)
        return 3
    warrior = _load_warrior_snapshot()
    diff = _diff(warrior, nova)
    _write_artifacts(nova, diff)
    print(
        "parity warrior={w} nova={n} both={b} warrior_only={wo} nova_only={no}".format(
            w=diff["counts"]["warrior"],
            n=diff["counts"]["nova"],
            b=diff["counts"]["both"],
            wo=diff["counts"]["warrior_only"],
            no=diff["counts"]["nova_only"],
        ),
        flush=True,
    )
    if not warrior:
        print(
            "note: no warrior_latest.json yet — warrior agent should snapshot "
            "Day Trade Dash HOD Momentum into .tmp/hod-momo-parity/warrior_latest.json",
            file=sys.stderr,
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Warrior ↔ Nova HOD parity observer")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=20.0)
    parser.add_argument("--skip-gate", action="store_true")
    args = parser.parse_args()

    if args.once:
        return run_once(args.url, require_gate=not args.skip_gate)

    while True:
        code = run_once(args.url, require_gate=not args.skip_gate)
        if code == 3:
            return 3
        time.sleep(max(5.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
