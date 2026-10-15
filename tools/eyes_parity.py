#!/usr/bin/env python3
"""Do the replayed eyes see what the live eyes saw? (#966)

For every trigger the live eyes journalled on a symbol-day that has a Session Record, the recording is
rebuilt through ``eyes.replay.EyesReplay`` -- the Sim eyes' own engine, in this process, read-only -- and
each live trigger is matched to the replay's trigger of the same setup within ``MATCH_SEC``. It reports
how many the replay rebuilt, at the same trigger level, the same second, the same tape verdict and the
same grade, and every trigger's row.

The live journal is what that day's code read. Two changes since make old lines unlike today's live
eyes, and the summary splits on them:

- the tape at a trigger is read when the lane sees the price, not at its stamp (f3d2cb0e, 2026-10-01);
- pace RVOL's expected volume follows the small-cap volume curve (65c1ba40, 2026-10-13), so grades
  before then used another RVOL.

The setup rules change too: a live line names its template and revision, and ``same_rules`` sums only
the triggers whose lane ran the revision the replay runs today.

A replay can only match a trigger whose price stream and candles it rebuilds. The live eyes follow
IBKR's L1 last, which a Session Record does not hold, so a replay steps on the recorded prints and the
archive's candles; triggers at another level or second read another tape.

Usage:

  py -3 tools/eyes_parity.py [--days 2026-10-09,2026-10-12] [--json OUT] [--env PATH]

It reads the desk's ``.env`` (``--env``; else ``NOVA_ENV_PATH``; else the main checkout's, also from a
worktree) for the data folders, and only its ``NOVA_*`` names. Nothing is written but ``--json``: the
leaderboard and the catalyst feed open read-only, and it stops, creating nothing, when the eyes'
journal, the Session Records or the bar archive is missing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
MATCH_SEC = 90.0          # a replay trigger of the same setup this close is the live one's
SAME_SECOND = 2.0         # the live stamp is IBKR's whole second; the replay's the end of its price second
READ_ON_ARRIVAL_SINCE = dt.datetime(2026, 10, 1, 4, 9, 42, tzinfo=dt.UTC).timestamp()     # f3d2cb0e
PACE_CURVE_SINCE = dt.datetime(2026, 10, 13, 15, 8, 6, tzinfo=dt.UTC).timestamp()        # 65c1ba40
WARMUP_SEC = 300.0        # a trigger in the recording's first minutes has no recorded run-up to rebuild
ET = ZoneInfo("America/New_York")
LEGACY_SETUP = "first_pullback"   # a line from before ADR 031 names no setup: the first pullback was the only one


def _main_checkout() -> Path:
    try:
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=REPO,
                                capture_output=True, text=True, check=True).stdout.strip()
        return Path(common).parent
    except (OSError, subprocess.CalledProcessError):
        return REPO


def load_desk_env(path: str | None) -> None:
    """The desk's ``NOVA_*`` data settings into this process (never printed); the desk's cache by default."""
    candidates = [Path(path)] if path else []
    if os.environ.get("NOVA_ENV_PATH"):
        candidates.append(Path(os.environ["NOVA_ENV_PATH"]))
    candidates += [_main_checkout() / ".env", REPO / ".env"]
    for env in candidates:
        if env.is_file():
            for line in env.read_text(encoding="utf-8").splitlines():
                name, sep, value = line.strip().partition("=")
                if sep and name.strip().startswith("NOVA_"):
                    os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))
            break
    os.environ.setdefault("NOVA_CACHE_DIR", str(_main_checkout() / "backend" / ".cache"))


def et(ts: float | None) -> str | None:
    return dt.datetime.fromtimestamp(ts, ET).strftime("%H:%M:%S") if ts else None


# -- pure: reading lines, matching, summing ---------------------------------------------------------
def rules_of(template: Any, rev: Any) -> str:
    return f"{template}@{rev}"


def trigger_of(event: dict[str, Any], grade: str | None) -> dict[str, Any]:
    return {"ts": float(event["ts"]), "setup_type": event.get("setup_type") or LEGACY_SETUP,
            "trigger": (event.get("setup") or {}).get("trigger"),
            "tape": (event.get("tape") or {}).get("verdict"), "grade": grade,
            "rules": rules_of(event.get("template"), event.get("rev"))}


def live_triggers(lines: Iterable[str], recorded: set[str]) -> dict[str, list[dict[str, Any]]]:
    """The live eyes' triggers by symbol (only symbols in ``recorded``), each with the newest grade the
    live eyes gave its setup before it. Only the lane in play counts -- the one whose triggers reach the
    bot; a template watched beside it (a chart-only 5-minute lane) journals its own; a line the journal
    holds twice counts once."""
    grades: dict[tuple, str] = {}
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line in lines:
        if '"source":"live"' not in line:
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        sym, setup = e.get("symbol"), e.get("setup_type") or LEGACY_SETUP
        if not sym or e.get("playing") is False:
            continue
        if e.get("grade"):
            grades[(sym, setup)] = e["grade"]
        if e.get("event") != "triggered" or sym not in recorded:
            continue
        if any(t["setup_type"] == setup and abs(t["ts"] - float(e["ts"])) < 1 for t in out[sym]):
            continue
        out[sym].append(trigger_of(e, grades.get((sym, setup))))
    return out


def compare(day: str, symbol: str, lives: list[dict], replays: list[dict], *, inside,
            rules: dict[str, str]) -> list[dict[str, Any]]:
    """One row per live trigger: the nearest replay trigger of its setup within ``MATCH_SEC``, or none.
    ``same_rules``: the live lane ran the template and revision the replay runs today (``rules``)."""
    rows = []
    for lv in lives:
        near = [r for r in replays if r["setup_type"] == lv["setup_type"] and abs(r["ts"] - lv["ts"]) <= MATCH_SEC]
        best = min(near, key=lambda r: abs(r["ts"] - lv["ts"])) if near else None
        rows.append({"day": day, "symbol": symbol, "setup": lv["setup_type"], "inside": bool(inside(lv["ts"])),
                     "same_rules": lv["rules"] == rules.get(lv["setup_type"]),
                     "live_ts": lv["ts"], "live_at": et(lv["ts"]), "replay_at": et(best["ts"]) if best else None,
                     "dt": round(best["ts"] - lv["ts"], 1) if best else None,
                     "live_trigger": lv["trigger"], "replay_trigger": best["trigger"] if best else None,
                     "live_tape": lv["tape"], "replay_tape": best["tape"] if best else None,
                     "live_grade": lv["grade"], "replay_grade": best["grade"] if best else None})
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The sums over every live trigger inside a recording, and over those whose lane ran today's rules."""
    return {"all": _sums(rows), "same_rules": _sums([r for r in rows if r["same_rules"]])}


def _sums(rows: list[dict[str, Any]]) -> dict[str, Any]:
    inside = [r for r in rows if r["inside"]]
    found = [r for r in inside if r["replay_at"] is not None]
    aligned = [r for r in found if r["live_trigger"] == r["replay_trigger"] and abs(r["dt"]) <= SAME_SECOND]
    tape_today = [r for r in aligned if r["live_ts"] >= READ_ON_ARRIVAL_SINCE]
    grade_today = [r for r in found if r["live_ts"] >= PACE_CURVE_SINCE]

    def same(items: list[dict], key: str) -> int:
        return sum(1 for r in items if r[f"live_{key}"] == r[f"replay_{key}"])

    return {
        "live_triggers_inside": len(inside),
        "rebuilt": len(found),
        "same_level": same(found, "trigger"),
        "same_second": sum(1 for r in found if abs(r["dt"]) <= SAME_SECOND),
        "aligned": len(aligned),
        "aligned_same_tape": same(aligned, "tape"),
        "aligned_read_on_arrival": len(tape_today),
        "aligned_read_on_arrival_same_tape": same(tape_today, "tape"),
        "rebuilt_same_grade": same(found, "grade"),
        "rebuilt_on_pace_curve": len(grade_today),
        "rebuilt_on_pace_curve_same_grade": same(grade_today, "grade"),
        "tape_pairs": Counter(f"{r['live_tape']}->{r['replay_tape']}" for r in found).most_common(),
        "grade_pairs": Counter(f"{r['live_grade']}->{r['replay_grade']}" for r in found).most_common(),
    }


# -- the run ----------------------------------------------------------------------------------------
def replay_triggers(rec: Any, templates: list, playing: dict) -> list[dict[str, Any]]:
    from eyes.replay import EyesReplay

    got: list[dict[str, Any]] = []
    grades: dict[str, str] = {}

    def journal(event: dict) -> None:
        if event.get("playing") is False:
            return
        if event.get("grade") and event.get("setup_type"):
            grades[event["setup_type"]] = event["grade"]
        if event.get("event") == "triggered":
            got.append(trigger_of(event, grades.get(event.get("setup_type"))))

    EyesReplay(rec, templates, source="parity", playing=playing, journal=journal).run_to_end()
    return got


def run(days: list[str] | None) -> list[dict[str, Any]]:
    sys.path.insert(0, str(REPO / "backend"))
    os.chdir(REPO / "backend")
    from capture.storage import capture_root
    from constants import ARCHIVE_DB_FILENAME
    from constants_bot import BOT_SCANNER_SETUPS
    from eyes.journal import journal_dir
    from eyes.recording import load
    from paths import cache_root
    from setup_templates.store import get_store

    root, journals = capture_root(create=False), journal_dir()
    missing = [str(p) for p in (journals, root, cache_root() / ARCHIVE_DB_FILENAME) if not p.exists()]
    if missing:
        raise SystemExit(f"eyes_parity reads the desk's data and creates none; missing: {', '.join(missing)}")

    store = get_store()
    templates = [t for s in BOT_SCANNER_SETUPS for t in store.templates(s) if not t.error]
    in_play = {s: store.in_play(s) for s in BOT_SCANNER_SETUPS}
    playing = {s: t.id for s, t in in_play.items()}
    rules = {s: rules_of(t.id, t.rev) for s, t in in_play.items()}
    rows: list[dict[str, Any]] = []
    for day in days or sorted(p.stem for p in journals.glob("*.jsonl")):
        if not (root / day).is_dir() or not (journals / f"{day}.jsonl").is_file():
            continue
        recorded = {p.name for p in (root / day).iterdir() if p.is_dir()}
        with (journals / f"{day}.jsonl").open(encoding="utf-8") as fh:
            lives = live_triggers(fh, recorded)
        for symbol, its in sorted(lives.items()):
            try:
                rec = load(day, symbol)
            except (ValueError, OSError) as exc:
                print(f"{day} {symbol}: skipped ({exc})", file=sys.stderr)
                continue

            def inside(ts: float, rec=rec) -> bool:
                return rec.recorded_at(ts) and rec.first_ts is not None and ts - rec.first_ts > WARMUP_SEC

            rows += compare(day, symbol, its, replay_triggers(rec, templates, playing), inside=inside, rules=rules)
            print(f"{day} {symbol}: {len(its)} live trigger(s)", file=sys.stderr)
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", default="", help="comma-separated YYYY-MM-DD; every journalled day by default")
    ap.add_argument("--json", default="", help="write every row here")
    ap.add_argument("--env", default=None, help="the desk's .env (data folders only)")
    args = ap.parse_args(argv)
    load_desk_env(args.env)
    rows = run([d for d in args.days.split(",") if d] or None)
    print(json.dumps(summarize(rows), indent=1))
    for r in rows:
        if r["inside"]:
            print(json.dumps({k: v for k, v in r.items() if k != "live_ts"}))
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
