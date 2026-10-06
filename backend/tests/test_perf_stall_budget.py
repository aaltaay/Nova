"""The longest stalls retain their full reports, and summaries track eviction (#619)."""
import json

from perf import recorder, stall_watch
from perf.store import PerfStore


def report(id, duration, at=3600.0):
    return {'id': id, 'duration_ms': duration, 'started_ts': at, 'ended_ts': at + duration / 1000,
            'loop': 'ib', 'samples': 1, 'stacks': [], 'top_frame': None, 'truncated': False}


def test_longer_replaces_shortest_tie_keeps_earlier_and_next_hour_is_independent(tmp_path, monkeypatch):
    monkeypatch.setattr('perf.store.PERF_STALL_FILES_PER_HOUR', 2)
    store = PerfStore(tmp_path)
    assert store.put_stall(report('short', 201))
    assert store.put_stall(report('medium', 1000))
    assert store.put_stall(report('long', 55000))
    assert not store.put_stall(report('tie', 1000))
    assert store.put_stall(report('next', 200, at=7200))
    store.drain()
    assert {p.stem for p in store.stalls_dir.glob('*.json')} == {'medium', 'long', 'next'}
    assert json.loads(store.stall_path('long').read_text())['duration_ms'] == 55000


def test_evicted_summary_loses_file_and_late_reports_remain_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr('perf.store.PERF_STALL_FILES_PER_HOUR', 1)
    store = PerfStore(tmp_path)
    recorder.reset_for_tests()
    recorder.configure(store)
    try:
        stall_watch.completed.put(report('short', 201))
        recorder.tick(now=3700)
        assert recorder.stall_summaries()[0]['file'] is not None
        stall_watch.completed.put(report('long', 55000))
        recorder.tick(now=3800)
        by_id = {s['id']: s for s in recorder.stall_summaries()}
        assert by_id['short']['file'] is None
        assert by_id['long']['file'] is not None
        assert store.put_stall(report('future', 200, at=14400))
        assert not store.put_stall(report('too-old', 99000))
    finally:
        recorder.reset_for_tests()


def test_a_full_write_queue_never_evicts_a_report_it_cannot_replace(tmp_path, monkeypatch):
    monkeypatch.setattr('perf.store.PERF_STALL_FILES_PER_HOUR', 1)
    store = PerfStore(tmp_path)
    assert store.put_stall(report('short', 201))
    store.drain()
    for _ in range(store._queue.maxsize):
        store.put({'kind': 'sample', 'ts': 3600})
    evicted = []
    assert not store.put_stall(report('long', 55000), evicted_ids=evicted)
    assert evicted == [] and store.retained_stall('short', 3600) is True
    assert store.stall_path('short').is_file()
