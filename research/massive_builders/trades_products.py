"""The two per-day products built from a day's raw trades file, and the day's movers both archives keep.

  A. trades_flow_v1/YYYY/MM/YYYY-MM-DD.parquet   one row per (ticker, minute): counts and shares by kind (off exchange,
     retail buy / sell by the sub-penny rule, midpoint, sweeps, odd lots, big prints, blocks, venues)
  B. trades_movers_v1/YYYY/MM/YYYY-MM-DD.parquet every raw trade of that day's movers and the lab's own names

Where the products live: ``archive_config.json`` "products_root" (default ``NOVA_MARKET_DATA_DIR``). Every column is
defined in ``docs/massive-builders.md``; ``FLOW_SELECT`` is the definition.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from massive_env import EDGE_LAB, NY, ROOT, TMP
from massive_bucket import sub

CONFIG = ROOT / "archive_config.json"   # {"raw_dirs": ["E:/Nova/massive/trades_v1", ...], "products_root": "E:/Nova/massive",
#                                            "keep_raw": true, "other_drive_floor_gb": 20}
EVT = EDGE_LAB / "data" / "evt"                                   # d=YYYY-MM-DD/part.parquet: the lab's event names of the day
EXTRA = EDGE_LAB / "data" / "archive_extra_tickers.parquet"       # (d, ticker): names whose raw trades are always kept


def config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def products_root() -> Path:
    """Where the two products are written (archive_config.json "products_root"; the log, the state, the aggregates
    and the scratch folder stay under ROOT)."""
    return Path(config().get("products_root") or ROOT)


def out_paths(d: date) -> tuple[Path, Path]:
    root = products_root()
    return root / "trades_flow_v1" / sub(d, ".parquet"), root / "trades_movers_v1" / sub(d, ".parquet")


def agg_file(dataset: str, d: date) -> Path:
    return ROOT / dataset / sub(d, ".csv.gz")


def prev_day_file(d: date) -> Path | None:
    for back in range(1, 8):
        p = agg_file("day_aggs_v1", d - timedelta(days=back))
        if p.exists():
            return p
    return None


def movers(con, d: date) -> int:
    """Temp table mv2(ticker): the day's movers (minute file + prior closes) and the lab's own names."""
    con.execute("CREATE OR REPLACE TEMP TABLE mv (ticker VARCHAR)")
    mf, pf = agg_file("minute_aggs_v1", d), prev_day_file(d)
    if mf.exists():
        prev = (f"(SELECT ticker, close AS pc FROM read_csv('{pf.as_posix()}', header = true))" if pf
                else "(SELECT NULL::VARCHAR AS ticker, NULL::DOUBLE AS pc WHERE false)")
        con.execute(f"""
            INSERT INTO mv
            SELECT a.ticker FROM (
                SELECT ticker, max(high) AS hi, min(low) AS lo, sum(volume * close) AS dv
                FROM read_csv('{mf.as_posix()}', header = true) GROUP BY ticker) a
            LEFT JOIN {prev} p USING (ticker)
            WHERE a.dv >= 1000000 AND a.hi <= 100 AND a.lo >= 1
              AND (a.hi / a.lo - 1 >= 0.20 OR (p.pc > 0 AND a.hi / p.pc - 1 >= 0.10))""")
    ev = EVT / f"d={d.isoformat()}" / "part.parquet"
    if ev.exists():
        con.execute(f"INSERT INTO mv SELECT DISTINCT ticker FROM read_parquet('{ev.as_posix()}')")
    if EXTRA.exists():
        con.execute(f"INSERT INTO mv SELECT DISTINCT ticker FROM read_parquet('{EXTRA.as_posix()}') WHERE d = '{d.isoformat()}'")
    con.execute("CREATE OR REPLACE TEMP TABLE mv2 AS SELECT DISTINCT ticker FROM mv WHERE ticker IS NOT NULL")
    return con.execute("SELECT count(*) FROM mv2").fetchone()[0]


SRC = """read_csv('{f}', header = true, compression = 'gzip', columns = {{'ticker': 'VARCHAR', 'conditions': 'VARCHAR', 'correction': 'INTEGER',
    'exchange': 'INTEGER', 'id': 'VARCHAR', 'participant_timestamp': 'BIGINT', 'price': 'DOUBLE', 'sequence_number': 'BIGINT',
    'sip_timestamp': 'BIGINT', 'size': 'DOUBLE', 'tape': 'INTEGER', 'trf_id': 'INTEGER', 'trf_timestamp': 'BIGINT'}})"""

# Prints that are not trades at the market when they print (average price, cash, derivatively priced, sold out of
# sequence in extended hours, next day, price variation, prior reference, seller, contingent): counted apart (np_vol).
# The official open / close records (15, 16) and the corrected close (38) repeat the auction print: left out.
NOT_MARKET = (2, 7, 10, 13, 20, 21, 22, 29, 52, 53)
_NM = " OR ".join(f"c LIKE '%,{k},%'" for k in NOT_MARKET)

FLOW_SELECT = """
  WITH t AS (
    SELECT ticker, exchange AS x, price AS p, size AS s, ',' || coalesce(conditions, '') || ',' AS c,
           CAST((sip_timestamp - {day0}) // 60000000000 AS INTEGER) AS m,
           CAST(round(price * 10000) AS BIGINT) % 100 AS z
    FROM {src}
    WHERE correction IN (0, 12) AND price > 0 AND size > 0
  ), u AS (
    SELECT *, (""" + _NM + """) AS nm FROM t
    WHERE c NOT LIKE '%,15,%' AND c NOT LIKE '%,16,%' AND c NOT LIKE '%,38,%' AND m BETWEEN 0 AND 1439
  )
  SELECT ticker, m,
         (count(*) FILTER (NOT nm))::INTEGER AS n, coalesce(sum(s) FILTER (NOT nm), 0)::BIGINT AS vol, coalesce(sum(s * p) FILTER (NOT nm), 0) AS dvol,
         coalesce(sum(s) FILTER (nm), 0)::BIGINT AS np_vol,
         (count(*) FILTER (NOT nm AND x = 4))::INTEGER AS off_n, coalesce(sum(s) FILTER (NOT nm AND x = 4), 0)::BIGINT AS off_vol,
         (count(*) FILTER (NOT nm AND x = 4 AND p >= 1 AND z BETWEEN 61 AND 99))::INTEGER AS rb_n,
         coalesce(sum(s) FILTER (NOT nm AND x = 4 AND p >= 1 AND z BETWEEN 61 AND 99), 0)::BIGINT AS rb_vol,
         (count(*) FILTER (NOT nm AND x = 4 AND p >= 1 AND z BETWEEN 1 AND 39))::INTEGER AS rs_n,
         coalesce(sum(s) FILTER (NOT nm AND x = 4 AND p >= 1 AND z BETWEEN 1 AND 39), 0)::BIGINT AS rs_vol,
         coalesce(sum(s) FILTER (NOT nm AND x = 4 AND p >= 1 AND z BETWEEN 40 AND 60), 0)::BIGINT AS mid_vol,
         (count(*) FILTER (NOT nm AND x <> 4 AND c LIKE '%,14,%'))::INTEGER AS iso_n,
         coalesce(sum(s) FILTER (NOT nm AND x <> 4 AND c LIKE '%,14,%'), 0)::BIGINT AS iso_vol,
         (count(*) FILTER (NOT nm AND (s < 100 OR c LIKE '%,37,%')))::INTEGER AS odd_n,
         coalesce(sum(s) FILTER (NOT nm AND (s < 100 OR c LIKE '%,37,%')), 0)::BIGINT AS odd_vol,
         (count(*) FILTER (NOT nm AND s * p >= 25000))::INTEGER AS big_n, coalesce(sum(s) FILTER (NOT nm AND s * p >= 25000), 0)::BIGINT AS big_vol,
         coalesce(sum(s) FILTER (NOT nm AND s * p >= 200000), 0)::BIGINT AS blk_vol,
         coalesce(max(s) FILTER (NOT nm), 0)::BIGINT AS max_sz,
         coalesce(sum(s) FILTER (NOT nm AND x = 12), 0)::BIGINT AS v_xnas, coalesce(sum(s) FILTER (NOT nm AND x = 10), 0)::BIGINT AS v_xnys,
         coalesce(sum(s) FILTER (NOT nm AND x = 11), 0)::BIGINT AS v_arcx, coalesce(sum(s) FILTER (NOT nm AND x = 19), 0)::BIGINT AS v_bats,
         coalesce(sum(s) FILTER (NOT nm AND x = 8), 0)::BIGINT AS v_edgx, coalesce(sum(s) FILTER (NOT nm AND x = 15), 0)::BIGINT AS v_iexg,
         coalesce(sum(s) FILTER (NOT nm AND x = 21), 0)::BIGINT AS v_memx, coalesce(sum(s) FILTER (NOT nm AND x IN (2, 7, 18)), 0)::BIGINT AS v_inv,
         coalesce(sum(s) FILTER (NOT nm AND c LIKE '%,12,%'), 0)::BIGINT AS ext_vol
  FROM u
  GROUP BY ticker, m ORDER BY ticker, m"""

FLOW = "\nCOPY (" + FLOW_SELECT + "\n) TO '{out}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 500000)"

RAW = """
COPY (
  SELECT t.ticker, t.sip_timestamp AS ts, t.participant_timestamp AS pts, t.price AS p, CAST(t.size AS INTEGER) AS s,
         CAST(t.exchange AS TINYINT) AS x, t.conditions AS c, CAST(t.correction AS TINYINT) AS corr, t.sequence_number AS seq,
         CAST(t.trf_id AS SMALLINT) AS trf
  FROM {src} t JOIN mv2 USING (ticker)
  ORDER BY t.ticker, t.sip_timestamp, t.sequence_number
) TO '{out}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 1000000)"""


def day0_ns(d: date) -> int:
    """Epoch nanoseconds of 00:00 America/New_York on d: minute m of the flow table is (sip_timestamp - this) // 60 s."""
    return int(datetime(d.year, d.month, d.day, tzinfo=NY).timestamp()) * 1_000_000_000


def flow_rows(con, src: str, day0: int) -> list[dict]:
    """The flow table's rows for one trades source (a ``read_csv(...)`` call or a table name), as ``process`` writes
    them, without writing a file."""
    cur = con.execute(FLOW_SELECT.format(src=src, day0=day0))
    names = [c[0] for c in cur.description]
    return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]


def process(d: date, raw: Path, threads: int = 3, mem: str = "2GB") -> dict:
    import duckdb
    a_out, b_out = out_paths(d)
    for p in (a_out, b_out):
        p.parent.mkdir(parents=True, exist_ok=True)
    day0 = day0_ns(d)
    con = duckdb.connect()
    con.execute(f"SET threads TO {threads}"); con.execute(f"SET memory_limit = '{mem}'")
    # one scratch folder per worker: DuckDB names its spill files the same in every process, and twelve workers sharing
    # one folder deleted and overwrote each other's (IO errors, then access violations that killed the workers)
    scratch = TMP / "duck" / str(os.getpid())
    scratch.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory = '{scratch.as_posix()}'")
    src = SRC.format(f=raw.as_posix())
    t0 = time.time()
    try:
        n_mv = movers(con, d)
        ta = a_out.with_name(a_out.name + ".tmp"); tb = b_out.with_name(b_out.name + ".tmp")
        con.execute(FLOW.format(src=src, day0=day0, out=ta.as_posix()))
        t1 = time.time()
        con.execute(RAW.format(src=src, out=tb.as_posix()))
        t2 = time.time()
        rows_a = con.execute(f"SELECT count(*), sum(n) FROM read_parquet('{ta.as_posix()}')").fetchone()
        rows_b = con.execute(f"SELECT count(*) FROM read_parquet('{tb.as_posix()}')").fetchone()[0]
    finally:
        con.close()
        shutil.rmtree(scratch, ignore_errors=True)
    ta.replace(a_out); tb.replace(b_out)
    return {"movers": n_mv, "flow_rows": rows_a[0], "trades": int(rows_a[1] or 0), "mover_trades": rows_b,
            "flow_mb": a_out.stat().st_size / 2**20, "movers_mb": b_out.stat().st_size / 2**20, "flow_s": t1 - t0, "raw_s": t2 - t1}
