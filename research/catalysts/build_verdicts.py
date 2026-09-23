"""Classify every target with the live desk's own classifier and report coverage.

Each target is judged at its own cutoff (09:30 for the pillar universe, the first top-10 minute
for a leaderboard mover) from the items of every source that answered for it. ``none_found``
means those sources looked and found nothing; a source that could not reach the date
(``out_of_range``) or had no id for the ticker (``unavailable``) is not counted as having looked.

Usage:  py -3 research/catalysts/build_verdicts.py [--json results/coverage.json]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict

from cat_config import RESULTS_DIR
from store import connect

from catalysts.classify import verdict  # the live desk's module (cat_config puts backend/ on the path)
from constants_catalysts import CATALYST_RULES_VERSION

CUTOFF_KIND = "target"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", default=str(RESULTS_DIR / "coverage.json"))
    a = ap.parse_args()
    con = connect()
    answered: dict[tuple[str, str], list[str]] = defaultdict(list)
    for ticker, day, source in con.execute("SELECT ticker, session_date, source FROM checks WHERE status = 'ok'"):
        answered[(ticker, day)].append(source)
    targets = con.execute("SELECT ticker, session_date, window_start, cutoff, window_end, origin FROM targets").fetchall()
    rows, by_origin, rep_source, sources_seen = [], defaultdict(Counter), Counter(), Counter()
    for ticker, day, w0, cut, _w1, origin in targets:
        items = [dict(zip(("title", "summary", "source", "publisher", "n_tickers", "form", "sec_items", "url",
                           "published_ts", "item_id"), r, strict=True)) for r in con.execute(
            "SELECT i.title, i.summary, i.source, i.publisher, i.n_tickers, i.form, i.sec_items, i.url, "
            "i.published_ts, i.item_id FROM item_tickers t JOIN items i USING (item_id) "
            "WHERE t.ticker = ? AND t.published_ts > ? AND t.published_ts <= ?", [ticker, w0, cut])]
        v = verdict(items, window_start=w0, cutoff=cut, sources_answered=answered.get((ticker, day), ()))
        best = next((it["item_id"] for it in items if it["title"] == v["title"] and it["source"] == v["source"]), None)
        rows.append((ticker, day, CUTOFF_KIND, CATALYST_RULES_VERSION, v["verdict"], v["category"], v["strength"],
                     best, v["source"], v["published_ts"], v["title"], ",".join(v["sources_answered"]), v["n_items"]))
        key = v["verdict"] + (f":{v['strength']}" if v["strength"] else "")
        by_origin[origin][key] += 1
        by_origin["all"][key] += 1
        if v["source"]:
            rep_source[v["source"]] += 1
        sources_seen[len(v["sources_answered"])] += 1
    with con:
        con.execute("DELETE FROM verdicts WHERE rules_version = ? AND cutoff_kind = ?", [CATALYST_RULES_VERSION, CUTOFF_KIND])
        con.executemany("INSERT INTO verdicts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    cats = Counter(r[5] for r in rows if r[4] == "catalyst")
    out = {"rules_version": CATALYST_RULES_VERSION, "targets": len(rows),
           "verdicts": {k: dict(v.most_common()) for k, v in by_origin.items()},
           "catalyst_categories": dict(cats.most_common()),
           "representative_source": dict(rep_source.most_common()),
           "sources_answered_per_target": dict(sorted(sources_seen.items()))}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(a.json, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
