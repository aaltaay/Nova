#!/usr/bin/env python3
"""Honest live-readiness scorecard (Phase I + Phase B). Never unlocks live.

Reads local API when available, else journal/archive SQLite. Exits 0 only when
every automatable gate is green AND human shadow-day criteria are met —
today that will fail until ≥5 paper shadow days and ≥50 non-mock closes exist.

  py -3 tools/live_readiness_scorecard.py
  py -3 tools/live_readiness_scorecard.py --json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

API = "http://127.0.0.1:8000"


def _get_json(path: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{API}{path}", timeout=3) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def _sql_count(db: Path, sql: str, args: tuple = ()) -> int:
    if not db.exists():
        return 0
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(sql, args).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def build_scorecard() -> dict:
    from constants import (
        JOURNAL_MIN_ADHERENCE_PCT_FOR_GO_LIVE,
        JOURNAL_MIN_TRADES_FOR_GO_LIVE,
        SLIPPAGE_MAX_ADVERSE_BPS,
    )
    from nova_os import control_mode

    cache = ROOT / "backend" / ".cache"
    journal_db = cache / "journal.db"
    archive_db = cache / "archive.db"

    ibkr = _get_json("/api/ibkr/status") or {}
    metrics = _get_json("/api/journal/metrics") or {}
    archive = _get_json("/api/archive/health") or {}
    executor = _get_json("/api/strategy/executor/status") or {}

    closed = int(metrics.get("total_closed_trades") or 0)
    if not metrics:
        closed = _sql_count(
            journal_db,
            "SELECT COUNT(*) FROM trades WHERE is_mock = 0 AND exit_price IS NOT NULL",
        )

    bars_1m = _sql_count(archive_db, "SELECT COUNT(*) FROM bars_1m")
    tape = _sql_count(archive_db, "SELECT COUNT(*) FROM tape_ibkr")

    # Shadow days: count filled rows in roadmap evidence is manual; check template.
    template = (ROOT / "docs" / "shadow-day-log-template.md").read_text(
        encoding="utf-8", errors="ignore"
    )
    # Naive: look for completed day markers in Roadmap-Status
    roadmap = (
        ROOT / "knowledge" / "obsidian" / "03-Nova-Decisions" / "Nova-Roadmap-Status.md"
    ).read_text(encoding="utf-8", errors="ignore")
    shadow_note = "0/5" in roadmap or "0 / 5" in roadmap

    auto_live_blocked = True
    try:
        control_mode.reset_for_tests()
        try:
            control_mode.set_mode("auto_live")
            auto_live_blocked = False
        except ValueError:
            auto_live_blocked = True
    except Exception:
        auto_live_blocked = True

    items = [
        {
            "id": "auto_live_rejected",
            "status": "PASS" if auto_live_blocked else "FAIL",
            "detail": "control_mode rejects auto_live",
        },
        {
            "id": "live_confirm_flag_off",
            "status": "PASS" if not ibkr.get("live_trading_confirmed", False) else "FAIL",
            "detail": f"live_trading_confirmed={ibkr.get('live_trading_confirmed')}",
        },
        {
            "id": "orders_not_live_armed",
            "status": "PASS" if ibkr.get("spend_status") != "live_armed" else "FAIL",
            "detail": f"spend_status={ibkr.get('spend_status')} mode={ibkr.get('mode')}",
        },
        {
            "id": "phase_b_paper_gateway",
            "status": (
                "PASS" if ibkr.get("mode") == "paper" or ibkr.get("gateway_mode") == "paper"
                else "FAIL"
            ),
            "detail": (
                f"Need paper Gateway for Phase B; current mode={ibkr.get('mode')} "
                f"gateway_mode={ibkr.get('gateway_mode')}"
            ),
        },
        {
            "id": "phase_b_shadow_days",
            "status": "FAIL",
            "detail": "Human: >=5 reviewed shadow days (Roadmap still 0/5)" if shadow_note
            else "Human: verify >=5 shadow days in Roadmap-Status",
        },
        {
            "id": "paper_sample_size",
            "status": "PASS" if closed >= JOURNAL_MIN_TRADES_FOR_GO_LIVE else "FAIL",
            "detail": f"closed_non_mock={closed} need>={JOURNAL_MIN_TRADES_FOR_GO_LIVE}",
        },
        {
            "id": "adherence",
            "status": (
                "PASS"
                if (metrics.get("adherence_pct") or 0) >= JOURNAL_MIN_ADHERENCE_PCT_FOR_GO_LIVE
                else "FAIL"
            ),
            "detail": (
                f"adherence_pct={metrics.get('adherence_pct')} "
                f"need>={JOURNAL_MIN_ADHERENCE_PCT_FOR_GO_LIVE}"
            ),
        },
        {
            "id": "expectancy_pl_ratio",
            "status": (
                "PASS" if (metrics.get("go_no_go") or {}).get("overall_go") else "FAIL"
            ),
            "detail": f"journal go_no_go={metrics.get('go_no_go')}",
        },
        {
            "id": "slippage_budget_constant",
            "status": "PASS",
            "detail": f"SLIPPAGE_MAX_ADVERSE_BPS={SLIPPAGE_MAX_ADVERSE_BPS} (measure in paper)",
        },
        {
            "id": "archive_bars_1m",
            "status": "PASS" if bars_1m > 0 else "FAIL",
            "detail": f"bars_1m={bars_1m} tape_ibkr={tape}",
        },
        {
            "id": "archive_r2",
            "status": "PASS" if (archive.get("r2") or {}).get("configured") else "PARTIAL",
            "detail": str(archive.get("r2")),
        },
        {
            # Restart default is signal; confirm/auto_paper are valid Phase B ladder steps.
            "id": "executor_ladder_ok",
            "status": (
                "PASS"
                if executor.get("control_mode", "signal") in ("signal", "confirm", "auto_paper")
                else "FAIL"
            ),
            "detail": f"control_mode={executor.get('control_mode')}",
        },
    ]

    passed = sum(1 for i in items if i["status"] == "PASS")
    failed = sum(1 for i in items if i["status"] == "FAIL")
    paper_ok = ibkr.get("mode") == "paper" or ibkr.get("gateway_mode") == "paper"
    overall = "GO" if failed == 0 else "NO-GO"
    return {
        "overall": overall,
        "passed": passed,
        "failed": failed,
        "items": items,
        "human_blocker": (
            (
                "Run Phase B shadow protocol >=5 days and accumulate >=50 closed "
                "non-mock paper brackets. Do not set IBKR_LIVE_TRADING_CONFIRMED "
                "until Live-Readiness flips to GO."
            )
            if paper_ok
            else (
                "Switch IB Gateway to PAPER, run Phase B shadow protocol >=5 days, "
                "accumulate >=50 closed non-mock paper brackets. Do not set "
                "IBKR_LIVE_TRADING_CONFIRMED until Live-Readiness flips to GO."
            )
        ),
        "template_present": "shadow-day" in template.lower(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    card = build_scorecard()
    if args.json:
        print(json.dumps(card, indent=2))
    else:
        print(f"OVERALL: {card['overall']}  ({card['passed']} pass / {card['failed']} fail)")
        for i in card["items"]:
            print(f"  [{i['status']:7}] {i['id']}: {i['detail']}")
        print()
        print("HUMAN BLOCKER:", card["human_blocker"])
    return 0 if card["overall"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
