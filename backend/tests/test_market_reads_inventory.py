"""The bulk index build's bookkeeping (``research/market_reads/inventory.py``, 2026-10-12): an index that was not
saved counts as a failure, so ``tools/market_data.py index`` never reports "0 failed" for a day still read the slow way."""
from __future__ import annotations

import gzip
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from market_reads import inventory  # noqa: E402
from sim import massive_index  # noqa: E402

pytestmark = pytest.mark.skipif(not massive_index.available(), reason="indexed_gzip is not installed")


@pytest.fixture
def day_file(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    path = tmp_path / "trades_v1" / "2026" / "09" / "2026-09-18.csv.gz"
    path.parent.mkdir(parents=True)
    with gzip.open(path, "wt", newline="") as fh:
        fh.write("ticker,price\nAA,1\nAAPL,2\n")
    return path


def test_a_built_index_is_built(day_file):
    assert inventory._build_one(str(day_file), 1 << 20)[1] == "built"
    assert inventory._build_one(str(day_file), 1 << 20)[1] == "current"


def test_an_index_that_was_not_saved_is_a_failure(day_file, monkeypatch):
    monkeypatch.setattr(massive_index, "_save", lambda *a, **k: None)      # a full disk or a read-only folder
    with pytest.raises(RuntimeError, match="not saved"):
        inventory._build_one(str(day_file), 1 << 20)


def test_a_file_another_build_holds_is_skipped(day_file, monkeypatch):
    lock = massive_index.path_for(day_file, day_file.parents[3])
    lock = lock.with_name(lock.name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("1")
    assert inventory._build_one(str(day_file), 1 << 20)[1].startswith("skipped")
