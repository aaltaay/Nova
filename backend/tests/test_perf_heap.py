"""Heap census (#619): what every full collection walks, named from a live process."""
from __future__ import annotations

import sys
import types
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from perf import heap

ET = ZoneInfo("America/New_York")


class Planted:
    def __init__(self, i: int) -> None:
        self.i = i
        self.rows = [i]


def setup_function() -> None:
    heap.reset_for_tests()


def test_census_names_a_planted_type_and_its_holders(monkeypatch):
    mod = types.ModuleType("perf_heap_planted")
    mod.__file__ = str(Path(heap.__file__).resolve().parents[1] / "perf_heap_planted.py")
    mod.BY_SYMBOL = {f"S{i}": [0] * 10 for i in range(300)}
    mod.PLANTED = [Planted(i) for i in range(20_000)]
    monkeypatch.setitem(sys.modules, "perf_heap_planted", mod)

    out = heap.census(top=400)

    assert out["schema_version"] == 1
    assert out["tracked"] > 20_000
    counts = {t["type"]: t["count"] for t in out["types"]}
    assert counts[f"{Planted.__module__}.{Planted.__qualname__}"] >= 20_000
    holders = {h["name"]: h for h in heap._holders()}
    assert holders["perf_heap_planted.BY_SYMBOL"]["items"] == 300
    assert holders["perf_heap_planted.BY_SYMBOL"]["nested_items"] == 3_000
    assert holders["perf_heap_planted.PLANTED"]["nested_items"] == 20_000   # each object's own list
    assert set(out["gc"]) == {"thresholds", "counts", "frozen", "stats"}


def test_a_young_census_is_answered_instead_of_walking_again(monkeypatch):
    calls: list[float] = []
    monkeypatch.setattr(heap, "census", lambda now=None: calls.append(now) or {"generated_at": now})
    persisted: list[dict] = []

    first = heap.latest(60, persisted.append)
    second = heap.latest(60, persisted.append)
    fresh = heap.latest(0, persisted.append)

    assert (first["cached"], second["cached"], fresh["cached"]) == (False, True, False)
    assert len(calls) == 2
    assert [p["kind"] for p in persisted] == ["heap", "heap"]


def _ts(month: int, day: int, hour: int, minute: int) -> float:
    return datetime(2026, month, day, hour, minute, tzinfo=ET).timestamp()


def test_no_scheduled_census_in_the_opening_minutes():
    assert heap.seconds_until_allowed(_ts(9, 30, 9, 30)) == 15 * 60     # a Wednesday
    assert heap.seconds_until_allowed(_ts(9, 30, 9, 24)) == 0
    assert heap.seconds_until_allowed(_ts(9, 30, 9, 45)) == 0
    assert heap.seconds_until_allowed(_ts(10, 3, 9, 30)) == 0           # a Saturday


def test_process_memory_says_what_the_platform_reports():
    mem = heap.process_memory()
    assert set(mem) == {"private_bytes", "working_set_bytes", "peak_working_set_bytes", "page_faults"}
    if sys.platform == "win32":
        assert mem["private_bytes"] > 0 and mem["working_set_bytes"] > 0
    else:
        assert mem["private_bytes"] is None
        assert mem["peak_working_set_bytes"] is None or mem["peak_working_set_bytes"] > 0


def test_route_answers_a_census():
    from main import app

    body = TestClient(app).get("/api/perf/heap").json()
    assert body["schema_version"] == 1
    assert body["cached"] is False
    assert body["types"] and body["tracked"] > 0


def test_class_level_caches_and_lru_caches_are_holders(monkeypatch):
    import functools

    mod = types.ModuleType("perf_heap_planted2")
    mod.__file__ = str(Path(heap.__file__).resolve().parents[1] / "perf_heap_planted2.py")

    class Registry:
        seen: dict = {}

    Registry.__module__ = "perf_heap_planted2"
    Registry.seen.update({i: [i] for i in range(50)})

    @functools.lru_cache(maxsize=None)
    def lookup(n: int) -> int:
        return n * 2

    for n in range(40):
        lookup(n)
    mod.Registry, mod.lookup = Registry, lookup
    monkeypatch.setitem(sys.modules, "perf_heap_planted2", mod)

    holders = {h["name"]: h for h in heap._holders()}
    assert holders["perf_heap_planted2.Registry.seen"]["items"] == 50
    assert holders["perf_heap_planted2.Registry.seen"]["nested_items"] == 50
    assert holders["perf_heap_planted2.lookup"] == {
        "name": "perf_heap_planted2.lookup", "kind": "lru_cache", "items": 40, "nested_items": 0}
