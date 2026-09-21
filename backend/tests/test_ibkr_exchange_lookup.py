"""Per-row scanner Exchange via a cold, paced qualified-contract lookup (#90).

The operator approved ONE IB round trip per NEW symbol on four conditions, and
each is pinned here: never awaited on admit (ADR 010 name-only admission), only
an empty ``row["exchange"]`` is filled, a failed or slow lookup still leaves a
usable row with a blank column, and no symbol is looked up twice.
"""
from __future__ import annotations

import asyncio
import time

import pytest

import exchanges as _exchanges
from ibkr import exchange_lookup as lookup
from ibkr import scanner_hydrate as hydrate


class _FakeContract:
    def __init__(self, primary_exchange: str | None):
        self.primaryExchange = primary_exchange
        self.exchange = "SMART"


class _FakeIb:
    """Minimal ib_async stand-in: records every qualify it is asked for."""

    def __init__(self, *, exchanges=None, connected=True, delay=0.0, fail=False):
        self.exchanges = exchanges or {}
        self.connected = connected
        self.delay = delay
        self.fail = fail
        self.calls: list[str] = []

    def isConnected(self) -> bool:  # noqa: N802 - ib_async API name
        return self.connected

    async def qualifyContractsAsync(self, contract):  # noqa: N802 - ib_async API name
        self.calls.append(contract.symbol)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("Gateway said no")
        exch = self.exchanges.get(contract.symbol)
        return [_FakeContract(exch)] if exch is not None else []


@pytest.fixture(autouse=True)
def _clean_lookup(monkeypatch):
    lookup.reset_for_tests()
    _exchanges.clear_ib_exchanges()
    # No IB loop supervisor in tests -- await the qualify on this loop.
    monkeypatch.setattr(lookup, "IBKR_EXCHANGE_LOOKUP_PACE_SEC", 0.0)
    yield
    lookup.reset_for_tests()
    _exchanges.clear_ib_exchanges()


def _use_ib(monkeypatch, ib) -> None:
    monkeypatch.setattr(lookup._client, "get_ib", lambda: ib)


def test_resolves_and_normalizes_a_new_symbol(monkeypatch):
    ib = _FakeIb(exchanges={"AAA": "ISLAND"})
    _use_ib(monkeypatch, ib)

    lookup.note_symbols(["AAA"])
    asyncio.run(lookup.drain_pending())

    assert ib.calls == ["AAA"]
    assert lookup.cached_exchange("AAA") == "NASDAQ"
    # Published so REST/WS serialization picks it up without a new roster batch.
    assert _exchanges.exchange_for("AAA") == "NASDAQ"


def test_same_symbol_is_never_looked_up_twice(monkeypatch):
    ib = _FakeIb(exchanges={"AAA": "NYSE"})
    _use_ib(monkeypatch, ib)

    lookup.note_symbols(["AAA", "AAA"])
    asyncio.run(lookup.drain_pending())
    lookup.note_symbols(["AAA"])
    asyncio.run(lookup.drain_pending())

    assert ib.calls == ["AAA"]


def test_a_failed_lookup_is_not_retried_and_leaves_the_column_blank(monkeypatch):
    ib = _FakeIb(exchanges={"AAA": "NYSE"}, fail=True)
    _use_ib(monkeypatch, ib)

    lookup.note_symbols(["AAA"])
    asyncio.run(lookup.drain_pending())
    lookup.note_symbols(["AAA"])
    asyncio.run(lookup.drain_pending())

    assert ib.calls == ["AAA"]
    assert lookup.cached_exchange("AAA") is None
    assert _exchanges.exchange_for("AAA") is None


def test_unrecognized_venue_stays_blank_so_the_filter_fails_open(monkeypatch):
    ib = _FakeIb(exchanges={"AAA": "SOME_DARK_VENUE"})
    _use_ib(monkeypatch, ib)

    lookup.note_symbols(["AAA"])
    asyncio.run(lookup.drain_pending())

    assert ib.calls == ["AAA"]
    assert lookup.cached_exchange("AAA") is None
    # normalize_ib_exchange refuses to guess, so nothing is published.
    assert _exchanges.exchange_for("AAA") is None


def test_disconnected_gateway_spends_nothing_and_re_queues(monkeypatch):
    offline = _FakeIb(connected=False)
    _use_ib(monkeypatch, offline)

    lookup.note_symbols(["AAA"])
    asyncio.run(lookup.drain_pending())

    assert offline.calls == []
    assert lookup.resolved_count() == 0

    online = _FakeIb(exchanges={"AAA": "NASDAQ"})
    _use_ib(monkeypatch, online)
    lookup.note_symbols(["AAA"])
    asyncio.run(lookup.drain_pending())

    assert online.calls == ["AAA"]
    assert lookup.cached_exchange("AAA") == "NASDAQ"


def test_queue_is_capped(monkeypatch):
    monkeypatch.setattr(lookup, "IBKR_EXCHANGE_LOOKUP_MAX_PENDING", 3)
    lookup.note_symbols([f"S{i}" for i in range(50)])
    assert lookup.pending_count() == 3


def test_note_rows_skips_rows_that_already_carry_an_exchange():
    lookup.note_rows([
        {"symbol": "AAA", "exchange": "NYSE"},
        {"symbol": "BBB", "exchange": None},
        {"symbol": "CCC"},
        {"symbol": ""},
    ])
    assert lookup.pending_count() == 2


# ── Admission must never wait on the lookup (ADR 010) ────────────────────────

def test_hydrate_rows_does_not_await_the_lookup(monkeypatch):
    """A Gateway that takes a minute to qualify must not delay a row."""
    ib = _FakeIb(exchanges={"AAA": "NASDAQ"}, delay=60.0)
    _use_ib(monkeypatch, ib)

    async def _scenario():
        started = time.perf_counter()
        rows = await hydrate.hydrate_rows(
            ["AAA"], table="gainers", session_key="2026-09-20",
        )
        elapsed = time.perf_counter() - started
        # Yield once so any background task gets a chance to run and stall.
        await asyncio.sleep(0)
        return rows, elapsed

    rows, elapsed = asyncio.run(_scenario())

    assert [r["symbol"] for r in rows] == ["AAA"]
    assert rows[0]["exchange"] is None      # blank, not blocked
    assert rows[0]["admitted_ts"] > 0       # the row is admitted and usable
    assert elapsed < 1.0, f"admission waited {elapsed:.2f}s on the IB lookup"


def test_hydrate_rows_queues_only_the_rows_without_an_exchange(monkeypatch):
    _use_ib(monkeypatch, _FakeIb(connected=False))
    # Inspect the queue itself, so no drain can empty it out from under us.
    monkeypatch.setattr(lookup, "_ensure_worker", lambda: None)

    asyncio.run(
        hydrate.hydrate_rows(
            ["AAA", "BBB"],
            table="gainers",
            session_key="2026-09-20",
            exchanges={"AAA": "NASDAQ"},
        )
    )
    assert lookup.pending_count() == 1


def test_hydrate_rows_backfills_only_an_empty_exchange():
    lookup._resolved["AAA"] = "ARCA"
    lookup._resolved["BBB"] = "ARCA"
    existing = [
        hydrate.stub_row("AAA", 1, exchange="NYSE"),   # scan already answered
        hydrate.stub_row("BBB", 2),                    # blank -> backfill
    ]

    rows = asyncio.run(
        hydrate.hydrate_rows(
            ["AAA", "BBB"],
            table="gainers",
            session_key="2026-09-20",
            existing=existing,
        )
    )

    by_sym = {r["symbol"]: r for r in rows}
    assert by_sym["AAA"]["exchange"] == "NYSE"   # never overwritten
    assert by_sym["BBB"]["exchange"] == "ARCA"


def test_scan_row_exchange_wins_over_the_lookup_cache():
    lookup._resolved["AAA"] = "ARCA"
    rows = asyncio.run(
        hydrate.hydrate_rows(
            ["AAA"],
            table="gainers",
            session_key="2026-09-20",
            exchanges={"AAA": "NASDAQ"},
        )
    )
    assert rows[0]["exchange"] == "NASDAQ"
