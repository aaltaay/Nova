"""The Massive dataset builders (research/massive_builders): import with no side effects, answer --help without a network,
read credentials only from the environment / .env, and turn a handful of synthetic trades into the exact flow and movers
columns trades_flow_v1 and trades_movers_v1 hold on disk.

Nothing here reads the operator's data drives or writes outside tmp_path.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

BUILDERS = Path(__file__).resolve().parents[2] / "research" / "massive_builders"
if str(BUILDERS) not in sys.path:
    sys.path.insert(0, str(BUILDERS))

import massive_env  # noqa: E402
import trades_products as tp  # noqa: E402

MODULES = ["massive_env", "massive_jobs", "massive_bucket", "trades_products", "raw_verify", "massive_archive", "quotes_archive",
           "reference_archive", "reference_status", "massive_access", "disk_scan", "verify_all", "massive_inventory"]
CLIS = ["massive_archive", "quotes_archive", "reference_archive", "verify_all", "massive_access", "massive_inventory"]

# trades_flow_v1 as read from the newest file on disk (pyarrow schema, 2026-10-18)
FLOW_COLUMNS = ["ticker", "m", "n", "vol", "dvol", "np_vol", "off_n", "off_vol", "rb_n", "rb_vol", "rs_n", "rs_vol", "mid_vol",
                "iso_n", "iso_vol", "odd_n", "odd_vol", "big_n", "big_vol", "blk_vol", "max_sz", "v_xnas", "v_xnys", "v_arcx",
                "v_bats", "v_edgx", "v_iexg", "v_memx", "v_inv", "ext_vol"]
MOVERS_SCHEMA = [("ticker", "VARCHAR"), ("ts", "BIGINT"), ("pts", "BIGINT"), ("p", "DOUBLE"), ("s", "INTEGER"), ("x", "TINYINT"),
                 ("c", "VARCHAR"), ("corr", "TINYINT"), ("seq", "BIGINT"), ("trf", "SMALLINT")]
QUOTES_SCHEMA = [("ticker", "VARCHAR"), ("ts", "BIGINT"), ("pts", "BIGINT"), ("bp", "DOUBLE"), ("bs", "INTEGER"), ("bx", "TINYINT"),
                 ("ap", "DOUBLE"), ("asz", "INTEGER"), ("ax", "TINYINT"), ("c", "VARCHAR"), ("ind", "VARCHAR"), ("seq", "BIGINT")]


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    """An empty folder the builders' data, lab and .env paths point into: it must stay empty."""
    box = tmp_path / "sandbox"
    box.mkdir()
    return box


def _sandbox_env(box: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update(NOVA_MARKET_DATA_DIR=str(box / "massive"), NOVA_EDGE_LAB_DIR=str(box / "lab"), NOVA_ENV_PATH=str(box / "absent.env"))
    for k in massive_env.KEYS:
        env.pop(k, None)
    return env


def test_every_module_imports_without_touching_the_disk(sandbox):
    code = f"import sys; sys.path.insert(0, {str(BUILDERS)!r}); " + "; ".join(f"import {m}" for m in MODULES)
    r = subprocess.run([sys.executable, "-c", code], env=_sandbox_env(sandbox), cwd=sandbox, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert list(sandbox.iterdir()) == []


@pytest.mark.parametrize("cli", CLIS)
def test_help_prints_the_usage_and_does_nothing_else(cli, sandbox):
    r = subprocess.run([sys.executable, str(BUILDERS / f"{cli}.py"), "--help"], env=_sandbox_env(sandbox), cwd=sandbox,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert "Research tooling" in r.stdout
    assert list(sandbox.iterdir()) == []


def test_credentials_come_from_the_env_file_and_the_process_env_wins(tmp_path, monkeypatch):
    env = tmp_path / "desk.env"
    env.write_text('MASSIVE_S3_ACCESS_KEY_ID="from-file"\nMASSIVE_API_KEY=file-key\n', encoding="utf-8")
    monkeypatch.setenv("NOVA_ENV_PATH", str(env))
    monkeypatch.setenv("MASSIVE_API_KEY", "process-key")
    vals = massive_env.env_values()
    assert vals["MASSIVE_S3_ACCESS_KEY_ID"] == "from-file"
    assert vals["MASSIVE_API_KEY"] == "process-key"


def test_no_personal_path_or_key_in_the_builders():
    bad = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]|AKIA[0-9A-Z]{16}|PRIVATE")
    hits = [f.name for f in BUILDERS.glob("*.py") if bad.search(f.read_text(encoding="utf-8"))]
    assert hits == []


# ---- the trades -> per-minute flow transformation ----------------------------------------------------------------------------
DAY = date(2026, 10, 16)
DAY0 = tp.day0_ns(DAY)


def _ts(minute: int, second: int = 0) -> int:
    return DAY0 + (minute * 60 + second) * 1_000_000_000


# (ticker, conditions, correction, exchange, price, size, sip_timestamp)
TRADES = [
    ("AAA", None, 0, 4, 10.0071, 100, _ts(570, 1)),     # off exchange, sub-penny .71 -> retail buy
    ("AAA", None, 0, 4, 10.0023, 50, _ts(570, 2)),      # off exchange, .23 -> retail sell; under 100 shares -> odd lot
    ("AAA", None, 0, 4, 10.005, 200, _ts(570, 3)),      # off exchange, .50 -> midpoint
    ("AAA", "14", 0, 12, 10.01, 300, _ts(570, 4)),      # intermarket sweep on Nasdaq
    ("AAA", None, 12, 11, 10.0, 3000, _ts(570, 5)),     # correction 12 still counts; $30,000 -> big print, Arca
    ("AAA", None, 0, 10, 10.0, 25000, _ts(570, 6)),     # $250,000 -> big print and block, NYSE
    ("AAA", "15", 0, 12, 10.0, 1000, _ts(570, 7)),      # official open record: left out
    ("AAA", "2", 0, 4, 10.0071, 500, _ts(570, 8)),      # average-price print: not a market trade (np_vol only)
    ("AAA", None, 1, 12, 10.0, 999, _ts(570, 9)),       # corrected-away trade: left out
    ("AAA", None, 0, 4, 0.5071, 100, _ts(571, 0)),      # off exchange under $1: no retail side
    ("AAA", "12,37", 0, 8, 10.0, 150, _ts(240, 0)),     # extended hours, odd-lot condition, EDGX
    ("AAA", None, 0, 4, 10.0, 70, _ts(1440, 0)),        # the next day: outside minutes 0-1439
    ("BBB", None, 0, 2, 5.0, 400, _ts(570, 0)),         # an inverted venue
]


def _trades_con():
    duckdb = pytest.importorskip("duckdb")
    con = duckdb.connect()
    con.execute("""CREATE TABLE trades (ticker VARCHAR, conditions VARCHAR, correction INTEGER, exchange INTEGER, id VARCHAR,
                   participant_timestamp BIGINT, price DOUBLE, sequence_number BIGINT, sip_timestamp BIGINT, size DOUBLE,
                   tape INTEGER, trf_id INTEGER, trf_timestamp BIGINT)""")
    con.executemany("INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [(t, c, corr, x, str(i), ts, p, i, ts, s, 3, 201 if x == 4 else None, None)
                     for i, (t, c, corr, x, p, s, ts) in enumerate(TRADES)])
    return con


def test_flow_rows_classify_each_trade_by_kind():
    rows = tp.flow_rows(_trades_con(), "trades", DAY0)
    assert list(rows[0]) == FLOW_COLUMNS
    by = {(r["ticker"], r["m"]): r for r in rows}
    assert list(by) == [("AAA", 240), ("AAA", 570), ("AAA", 571), ("BBB", 570)]
    a = by[("AAA", 570)]
    assert (a["n"], a["vol"], a["np_vol"]) == (6, 28650, 500)
    assert a["dvol"] == pytest.approx(286504.825)
    assert (a["off_n"], a["off_vol"]) == (3, 350)
    assert (a["rb_n"], a["rb_vol"], a["rs_n"], a["rs_vol"], a["mid_vol"]) == (1, 100, 1, 50, 200)
    assert (a["iso_n"], a["iso_vol"]) == (1, 300)
    assert (a["odd_n"], a["odd_vol"]) == (1, 50)
    assert (a["big_n"], a["big_vol"], a["blk_vol"], a["max_sz"]) == (2, 28000, 25000, 25000)
    assert (a["v_xnas"], a["v_xnys"], a["v_arcx"], a["v_inv"], a["ext_vol"]) == (300, 25000, 3000, 0, 0)
    sub_dollar = by[("AAA", 571)]
    assert (sub_dollar["off_n"], sub_dollar["off_vol"], sub_dollar["rb_n"], sub_dollar["rs_n"], sub_dollar["mid_vol"]) == (1, 100, 0, 0, 0)
    pre = by[("AAA", 240)]
    assert (pre["ext_vol"], pre["odd_n"], pre["odd_vol"], pre["v_edgx"], pre["off_n"]) == (150, 1, 150, 150, 0)
    assert by[("BBB", 570)]["v_inv"] == 400


def test_movers_product_keeps_every_raw_trade_of_the_movers(tmp_path):
    con = _trades_con()
    con.execute("CREATE TEMP TABLE mv2 AS SELECT 'AAA' AS ticker")
    out = tmp_path / "movers.parquet"
    con.execute(tp.RAW.format(src="trades", out=out.as_posix()))
    schema = [(c[0], c[1]) for c in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{out.as_posix()}')").fetchall()]
    assert schema == MOVERS_SCHEMA
    ts = [r[0] for r in con.execute(f"SELECT ts FROM read_parquet('{out.as_posix()}')").fetchall()]
    assert len(ts) == sum(1 for t in TRADES if t[0] == "AAA") and ts == sorted(ts)


def test_quotes_movers_product_columns(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    import quotes_archive as qa
    con = duckdb.connect()
    con.execute("""CREATE TABLE quotes (ticker VARCHAR, ask_exchange INTEGER, ask_price DOUBLE, ask_size DOUBLE, bid_exchange INTEGER,
                   bid_price DOUBLE, bid_size DOUBLE, conditions VARCHAR, indicators VARCHAR, participant_timestamp BIGINT,
                   sequence_number BIGINT, sip_timestamp BIGINT, tape INTEGER, trf_timestamp BIGINT)""")
    con.execute("INSERT INTO quotes VALUES ('AAA', 12, 10.02, 3, 11, 10.0, 5, '1', '604', 1, 1, 1, 3, NULL), "
                "('ZZZ', 12, 1.0, 1, 11, 0.9, 1, NULL, NULL, 2, 2, 2, 3, NULL)")
    con.execute("CREATE TEMP TABLE mv2 AS SELECT 'AAA' AS ticker")
    out = tmp_path / "quotes.parquet"
    con.execute(qa.QRAW.format(src="quotes", out=out.as_posix()))
    schema = [(c[0], c[1]) for c in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{out.as_posix()}')").fetchall()]
    assert schema == QUOTES_SCHEMA
    assert con.execute(f"SELECT ticker, bp, asz FROM read_parquet('{out.as_posix()}')").fetchall() == [("AAA", 10.0, 3)]
