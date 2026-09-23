"""Hand-labelled accuracy check for the catalyst classifier.

  export   a stratified sample of items (every predicted class, every source) to
           ``labels/sample.csv`` -- ``label_kind`` / ``label_category`` left blank for a person
  score    compare a labelled CSV with what the classifier says now: accuracy on kind
           (catalyst / negative / routine / noise), the confusion table, and every miss

The labeller reads the headline (and, for a filing, the release's opening) and answers the
question the classifier answers: is this the company's own news that could move the stock,
dilution, a routine item, or noise?

Usage:
    py -3 research/catalysts/labels.py export [--n 200] [--seed 7] [--name holdout.csv --exclude labels/sample.csv]
    py -3 research/catalysts/labels.py score labels/sample_claude.csv [labels/sample_operator.csv ...]
"""
from __future__ import annotations

import argparse
import csv
import random
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from cat_config import ET, LABELS_DIR
from store import connect

from catalysts.classify import classify_item

FIELDS = ["item_id", "source", "published_et", "tickers", "publisher", "form", "sec_items", "title", "summary",
          "label_kind", "label_category", "notes"]


def predicted(row: dict) -> tuple[str, str, str | None]:
    lb = classify_item(row["title"], row.get("summary"), source=row["source"], publisher=row.get("publisher") or "",
                       n_tickers=int(row["n_tickers"]) if row.get("n_tickers") not in (None, "") else None,
                       form=row.get("form") or None, sec_items=row.get("sec_items") or None)
    return lb.kind, lb.category, lb.strength


def export(n: int, seed: int, name: str = "sample.csv", exclude: list[str] | None = None) -> Path:
    con = connect()
    skip = set()
    for x in exclude or []:
        with open(x, encoding="utf-8-sig", newline="") as f:
            skip |= {r["item_id"] for r in csv.DictReader(f)}
    rows = [dict(zip(("item_id", "source", "published_ts", "title", "summary", "publisher", "n_tickers", "form",
                      "sec_items", "tickers"), r, strict=True)) for r in con.execute(
        "SELECT i.item_id, i.source, i.published_ts, i.title, i.summary, i.publisher, i.n_tickers, i.form, i.sec_items, "
        "group_concat(t.ticker) FROM items i JOIN item_tickers t USING (item_id) "
        "WHERE EXISTS (SELECT 1 FROM targets g WHERE g.ticker = t.ticker AND t.published_ts > g.window_start "
        "AND t.published_ts <= g.cutoff) GROUP BY i.item_id")]
    strata: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if r["item_id"] in skip:
            continue
        kind, cat, _ = predicted(r)
        strata[(kind, cat, r["source"])].append(r)
    rng = random.Random(seed)
    keys = sorted(strata)
    per = max(1, n // len(keys))
    sample = []
    for k in keys:  # every class x source is represented; big strata give up the rest proportionally
        sample += rng.sample(strata[k], min(per, len(strata[k])))
    rest = [r for k in keys for r in strata[k] if r not in sample]
    sample += rng.sample(rest, max(0, min(n - len(sample), len(rest))))
    rng.shuffle(sample)
    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    path = LABELS_DIR / name
    with open(path, "w", encoding="utf-8-sig", newline="") as f:  # predictions are deliberately not written: blind labels
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in sample:
            w.writerow({"item_id": r["item_id"], "source": r["source"],
                        "published_et": datetime.fromtimestamp(r["published_ts"], ET).strftime("%Y-%m-%d %H:%M"),
                        "tickers": r["tickers"], "publisher": r["publisher"], "form": r["form"], "sec_items": r["sec_items"],
                        "title": r["title"], "summary": (r["summary"] or "")[:400] if r["source"] == "edgar" else "",
                        "label_kind": "", "label_category": "", "notes": ""})
    print(f"{len(sample)} items from {len(rows)} ({len(keys)} strata) -> {path}")
    return path


def score(paths: list[str]) -> None:
    con = connect()
    for p in paths:
        with open(p, encoding="utf-8-sig", newline="") as f:
            labelled = [r for r in csv.DictReader(f) if r.get("label_kind")]
        conf, misses = Counter(), []
        for r in labelled:
            db = con.execute("SELECT title, summary, source, publisher, n_tickers, form, sec_items FROM items WHERE item_id = ?",
                             [r["item_id"]]).fetchone()
            row = dict(zip(("title", "summary", "source", "publisher", "n_tickers", "form", "sec_items"), db, strict=True))
            kind, cat, strength = predicted(row)
            conf[(r["label_kind"], kind)] += 1
            if r["label_kind"] != kind:
                misses.append((r["label_kind"], kind, cat, (row["title"] or "")[:110]))
        total = sum(conf.values())
        right = sum(v for (a, b), v in conf.items() if a == b)
        kinds = sorted({k for pair in conf for k in pair})
        print(f"\n== {p}: {right}/{total} = {right / total:.0%} agree on kind")
        print("labelled \\ predicted  " + "  ".join(f"{k:>9s}" for k in kinds))
        for a in kinds:
            print(f"{a:>20s}  " + "  ".join(f"{conf[(a, b)]:9d}" for b in kinds))
        catalyst_true = sum(v for (a, b), v in conf.items() if a == "catalyst" and b == "catalyst")
        pred_cat = sum(v for (a, b), v in conf.items() if b == "catalyst")
        real_cat = sum(v for (a, b), v in conf.items() if a == "catalyst")
        if pred_cat and real_cat:
            print(f"catalyst precision {catalyst_true / pred_cat:.0%}, recall {catalyst_true / real_cat:.0%}")
        for m in misses:
            print(f"  labelled {m[0]:9s} predicted {m[1]:9s} ({m[2]}): {m[3]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--n", type=int, default=200)
    e.add_argument("--seed", type=int, default=7)
    e.add_argument("--name", default="sample.csv")
    e.add_argument("--exclude", nargs="*", default=[], help="labelled CSVs whose items a holdout must not repeat")
    s = sub.add_parser("score")
    s.add_argument("paths", nargs="+")
    a = ap.parse_args()
    if a.cmd == "export":
        export(a.n, a.seed, a.name, a.exclude)
    else:
        score(a.paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
