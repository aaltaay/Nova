"""The session commission read is kept in memory until the ledger changes (#554).

The account / positions polls and the Live bot breaker read this session's
CommissionReport dollars about once a second on the HTTP loop. The sum is kept
until the next write to ``executions`` (``execution.ledger_generation``), another
session start or another ledger file -- exact, no TTL. These tests pin all
three, and fail on a write to ``executions`` that does not advance the
generation.
"""
from __future__ import annotations

import ast
import os
import re
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from execution import evidence_store, ledger_generation, store, store_facts
from execution.store_schema import SCHEMA

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def opens(monkeypatch) -> dict:
    """Counts ledger connections: a kept read opens none."""
    calls = {"n": 0}
    real = store.get_connection

    def counting():
        calls["n"] += 1
        return real()

    monkeypatch.setattr(store, "get_connection", counting)
    return calls


@pytest.fixture
def stable_identity(monkeypatch):
    """As on Windows, where a ledger file's identity is its creation time and a
    write does not change it: only the generation can refresh the read. (On
    Linux the change time moves after a write, which would hide a missing bump.)"""
    monkeypatch.setattr(ledger_generation, "file_key", lambda path: (str(path), "born"))


def _read(since_ts: float = 0.0) -> dict[str, float]:
    return store_facts.session_commission_by_symbol(since_ts=since_ts)


def _place(
    key: str,
    *,
    symbol: str = "IVF",
    order_id: int = 0,
    status: str | None = None,
    broker_status: str | None = None,
    filled_qty: float | None = 1.0,
    commission: float | None = 1.0,
) -> str:
    execution_id, is_new = store.reserve(
        idempotency_key=key, operation="place", source="manual",
        symbol=symbol, received_ns=1, payload={"qty": 1, "side": "BUY"},
    )
    assert is_new
    store.update_stages(
        execution_id, order_id=order_id or None, status=status, broker_status=broker_status,
    )
    store_facts.record_broker_facts(
        execution_id, filled_qty=filled_qty, commission=commission,
    )
    return execution_id


# -- a kept read ---------------------------------------------------------------


def test_a_repeat_read_opens_no_connection(opens):
    _place("kept-1", status="filled", commission=1.25)
    opens["n"] = 0
    assert _read() == {"IVF": 1.25}
    assert opens["n"] > 0

    opens["n"] = 0
    assert _read() == {"IVF": 1.25}
    assert _read() == {"IVF": 1.25}
    assert opens["n"] == 0


def test_the_positions_poll_and_the_breaker_read_memory(opens, monkeypatch):
    """The callers #554 names: ``/api/ibkr/account`` and ``/positions`` (through
    ``attach_session_commissions``) and the Live bot breaker."""
    from bot.day_pnl import session_commission_total
    from ibkr.position_commission import attach_session_commissions

    monkeypatch.setattr("execution.closed_blotter.session_start_ts", lambda: 0.0)
    _place("callers-1", status="filled", commission=1.5)
    opens["n"] = 0
    assert attach_session_commissions([{"symbol": "IVF", "qty": 1}])[0]["commission"] == 1.5
    assert opens["n"] > 0

    opens["n"] = 0
    for _ in range(3):
        assert attach_session_commissions([{"symbol": "IVF", "qty": 1}])[0]["commission"] == 1.5
        assert session_commission_total() == 1.5
    assert opens["n"] == 0


def test_the_kept_value_is_never_handed_out():
    _place("copy-1", status="filled", commission=1.0)
    first = _read()
    first["IVF"] = 99.0
    first["ZTG"] = 5.0
    assert _read() == {"IVF": 1.0}


def test_a_failed_read_keeps_nothing(monkeypatch):
    _place("fail-1", status="filled", commission=1.0)
    real = store_facts.list_session_placed

    def broken(**_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(store_facts, "list_session_placed", broken)
    with pytest.raises(sqlite3.OperationalError):
        _read()
    monkeypatch.setattr(store_facts, "list_session_placed", real)
    assert _read() == {"IVF": 1.0}


# -- every write refreshes the next read ----------------------------------------


def _write_reserve(_eid: str) -> None:
    store.reserve(
        idempotency_key="another", operation="place", source="manual",
        symbol="ZTG", received_ns=2,
    )


def _write_update_stages(eid: str) -> None:
    store.update_stages(eid, error="note")


def _write_ack(_eid: str) -> None:
    store.mark_ack_by_order_id(4401, 11, broker_status="Submitted")


def _write_ack_upgrade(_eid: str) -> None:
    store.mark_ack_by_order_id(4401, 12, broker_status="Submitted", allow_status_upgrade=True)


def _write_filled(_eid: str) -> None:
    store.mark_filled_by_order_id(4401, 13)


def _write_facts(eid: str) -> None:
    store_facts.record_broker_facts(eid, perm_id=990001)


def _write_cancel_mark(_eid: str) -> None:
    store_facts.mark_place_cancelled(order_id=4402)


def _write_payload(eid: str) -> None:
    evidence_store.merge_execution_payload(eid, {"note": "x"})


def _write_fill_evidence(eid: str) -> None:
    evidence_store.record_fill(
        execution_id=eid, order_id=4401, provenance="execDetails", complete=False,
        price=1.0, shares=1.0, cumulative_shares=1.0,
    )


@pytest.mark.parametrize(
    "write",
    [
        _write_reserve, _write_update_stages, _write_ack, _write_ack_upgrade,
        _write_filled, _write_facts, _write_cancel_mark, _write_payload,
        _write_fill_evidence,
    ],
    ids=lambda f: f.__name__.removeprefix("_write_"),
)
def test_every_ledger_write_advances_the_generation_and_the_next_read_queries(
    write, stable_identity, opens,
):
    eid = _place("gen-1", order_id=4401, status="sent", broker_status="Cancelled")
    _place("gen-2", order_id=4402, status="acked", broker_status="Submitted",
           filled_qty=None, commission=None)
    _read()
    opens["n"] = 0
    _read()
    assert opens["n"] == 0

    before = ledger_generation.current()
    write(eid)
    assert ledger_generation.current() > before
    opens["n"] = 0
    _read()
    assert opens["n"] > 0


def test_update_stages_closing_a_row_is_read_next(stable_identity):
    eid = _place("stages-1", status="acked", broker_status="Submitted")
    assert _read() == {}
    store.update_stages(eid, status="filled")
    assert _read() == {"IVF": 1.0}


def test_a_commission_report_is_read_next(stable_identity):
    eid = _place("facts-1", status="filled", commission=None)
    assert _read() == {}
    store_facts.record_broker_facts(eid, commission=1.25)
    assert _read() == {"IVF": 1.25}
    store_facts.record_broker_facts(eid, commission=2.5)
    assert _read() == {"IVF": 2.5}


def test_a_first_ack_that_closes_a_row_is_read_next(stable_identity):
    _place("ack-1", order_id=5501, status="sent")
    assert _read() == {}
    assert store.mark_ack_by_order_id(5501, 21, broker_status="Filled")
    assert _read() == {"IVF": 1.0}


def test_an_ack_upgrade_that_reopens_a_row_is_read_next(stable_identity):
    _place("upgrade-1", order_id=5502, status="acked", broker_status="Cancelled")
    assert _read() == {"IVF": 1.0}
    assert store.mark_ack_by_order_id(
        5502, 22, broker_status="Submitted", allow_status_upgrade=True,
    )
    assert _read() == {}


def test_a_late_fill_is_read_next(stable_identity):
    _place("filled-1", order_id=5503, status="acked", broker_status="Submitted")
    assert _read() == {}
    assert store.mark_filled_by_order_id(5503, 23)
    assert _read() == {"IVF": 1.0}


def test_a_write_on_the_persist_worker_thread_is_read_next(stable_identity):
    """IB-callback writes land on ``execution.persist_queue``'s thread."""
    eid = _place("thread-1", status="filled", commission=None)
    assert _read() == {}
    worker = threading.Thread(
        target=store_facts.record_broker_facts, args=(eid,), kwargs={"commission": 0.35},
    )
    worker.start()
    worker.join()
    assert _read() == {"IVF": 0.35}


class _Conn:
    def commit(self) -> None:
        pass


def test_a_result_computed_while_a_write_lands_is_not_served_again(tmp_path):
    ledger = tmp_path / "ledger.db"
    ledger.write_bytes(b"")

    def racing() -> dict[str, float]:
        ledger_generation.commit(_Conn())  # a write lands mid-query
        return {"IVF": 1.0}

    assert ledger_generation.session_commissions(0.0, ledger, racing) == {"IVF": 1.0}
    assert ledger_generation.session_commissions(0.0, ledger, lambda: {"IVF": 2.0}) == {"IVF": 2.0}
    assert ledger_generation.session_commissions(0.0, ledger, lambda: {"IVF": 3.0}) == {"IVF": 2.0}


def test_a_slow_read_never_replaces_a_newer_one(tmp_path):
    ledger = tmp_path / "ledger.db"
    ledger.write_bytes(b"")

    def slow() -> dict[str, float]:
        ledger_generation.commit(_Conn())  # a write lands mid-query ...
        newer = ledger_generation.session_commissions(0.0, ledger, lambda: {"IVF": 2.0})
        assert newer == {"IVF": 2.0}  # ... and a newer read is kept meanwhile
        return {"IVF": 1.0}

    def must_not_run() -> dict[str, float]:
        raise AssertionError("the newer read was replaced by the slow one")

    assert ledger_generation.session_commissions(0.0, ledger, slow) == {"IVF": 1.0}
    assert ledger_generation.session_commissions(0.0, ledger, must_not_run) == {"IVF": 2.0}


def test_a_commit_that_raises_still_advances_the_generation():
    class _Failing:
        def commit(self) -> None:
            raise sqlite3.OperationalError("disk I/O error")

    before = ledger_generation.current()
    with pytest.raises(sqlite3.OperationalError):
        ledger_generation.commit(_Failing())
    assert ledger_generation.current() == before + 1


# -- a new session start, another ledger file -----------------------------------


def test_a_new_session_start_is_read_again(opens):
    _place("session-1", status="filled", commission=1.0)
    assert _read(0.0) == {"IVF": 1.0}
    opens["n"] = 0
    assert _read(time.time() + 3600) == {}
    assert opens["n"] > 0


def test_another_ledger_file_is_read_again(monkeypatch, tmp_path, opens):
    _place("file-1", status="filled", commission=1.0)
    assert _read() == {"IVF": 1.0}
    other = tmp_path / "other_cache"
    other.mkdir()
    monkeypatch.setenv("NOVA_CACHE_DIR", str(other))
    opens["n"] = 0
    assert _read() == {}
    assert opens["n"] > 0


def test_a_ledger_replaced_at_the_same_path_is_read_again():
    """An operator restoring a ledger writes no row through Nova: only the
    file's identity says it changed."""
    _place("replace-1", status="filled", commission=1.0)
    assert _read() == {"IVF": 1.0}
    path = store._db_path()
    generation = ledger_generation.current()
    # Built beside the ledger, then moved over it: a new file, never a write
    # through Nova (and a new file id even where change times are coarse).
    restored = path.with_name("restored.db")
    now = time.time()
    conn = sqlite3.connect(restored)
    try:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO executions (id, idempotency_key, operation, source, symbol, status,"
            " boot_id, received_ns, created_ts, updated_ts, filled_qty, commission)"
            " VALUES ('r', 'r', 'place', 'manual', 'ZTG', 'filled', 'b', 1, ?, ?, 1, 2.0)",
            (now, now),
        )
        conn.commit()
    finally:
        conn.close()
    for suffix in ("-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)
    os.replace(restored, path)

    assert ledger_generation.current() == generation
    assert _read() == {"ZTG": 2.0}


# -- no write to ``executions`` skips the generation ------------------------------

# Data writes only: the schema's CREATE / ALTER run once per ledger file inside
# ``store.init_db``, before any read of that file is kept, and change no row.
_WRITE_SQL = re.compile(
    r"\b(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|REPLACE\s+INTO|UPDATE(?:\s+OR\s+\w+)?|DELETE\s+FROM)"
    r"\s+[\"'`\[]?executions\b",
    re.IGNORECASE,
)
_KNOWN_WRITERS = {
    "execution/store.py:reserve",
    "execution/store.py:update_stages",
    "execution/store.py:mark_ack_by_order_id",
    "execution/store.py:mark_filled_by_order_id",
    "execution/store_facts.py:record_broker_facts",
    "execution/store_facts.py:mark_place_cancelled",
    "execution/evidence_store.py:merge_execution_payload",
    "execution/evidence_store.py:record_fill",
}


def _docstrings(tree: ast.AST) -> set[int]:
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                out.add(id(body[0].value))
    return out


class _Writes(ast.NodeVisitor):
    def __init__(self, docstrings: set[int]) -> None:
        self.docstrings = docstrings
        self.stack: list[ast.AST] = []
        self.found: list[tuple[ast.AST | None, int]] = []

    def visit_FunctionDef(self, node) -> None:
        self.stack.append(node)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Constant(self, node: ast.Constant) -> None:
        if (
            isinstance(node.value, str)
            and id(node) not in self.docstrings
            and _WRITE_SQL.search(node.value)
        ):
            self.found.append((self.stack[-1] if self.stack else None, node.lineno))


def _commits_through_the_generation(func: ast.AST) -> bool:
    commits = [
        node for node in ast.walk(func)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "commit"
    ]
    return bool(commits) and all(
        isinstance(c.func.value, ast.Name) and c.func.value.id == "ledger_generation"
        for c in commits
    )


def test_every_write_to_executions_commits_through_the_generation():
    writers: set[str] = set()
    offenders: list[str] = []
    for path in sorted(BACKEND.rglob("*.py")):
        rel = path.relative_to(BACKEND).as_posix()
        if rel.startswith("tests/") or "__pycache__" in rel:
            continue
        source = path.read_text(encoding="utf-8")
        if not re.search(r"executions", source, re.IGNORECASE):
            continue
        tree = ast.parse(source)
        visitor = _Writes(_docstrings(tree))
        visitor.visit(tree)
        for func, line in visitor.found:
            if func is None:
                offenders.append(f"{rel}:{line} writes executions outside a function")
                continue
            name = f"{rel}:{func.name}"
            writers.add(name)
            if not _commits_through_the_generation(func):
                offenders.append(
                    f"{name} (line {line}) writes executions without "
                    "ledger_generation.commit(conn) for every commit",
                )
    assert not offenders, offenders
    assert _KNOWN_WRITERS <= writers, sorted(_KNOWN_WRITERS - writers)
