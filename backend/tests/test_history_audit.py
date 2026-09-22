"""Historical replay adversarial API, database lifecycle and worker failures."""
from __future__ import annotations

import asyncio
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sim import history_download as download, history_playback as playback
from sim import history_routes as routes, history_store as store, session_clock as clock


@pytest.fixture
def client(tmp_path, monkeypatch):
    from archive import db
    from sim import mode
    monkeypatch.setenv('NOVA_SIM_HISTORY_DIR', str(tmp_path / 'history'))
    monkeypatch.setattr(db, 'cache_dir', lambda: tmp_path)
    monkeypatch.setattr(mode, 'is_sim_mode', lambda: True)
    db.init_db()
    app = FastAPI()
    app.include_router(routes.router)
    playback.clear()
    clock.reset_for_tests()
    yield TestClient(app)
    playback.clear()
    clock.reset_for_tests()


@pytest.mark.parametrize('fields', [
    {'start': '09:30', 'end': '04:00'},
    {'start': '20:00', 'end': '04:00'},
    {'date': '2999-09-18'},
    {'date': '2026-09-18/2026-09-19'},
    {'end': '24:00'},
    {'symbol': '../not-a-ticker'},
])
def test_adversarial_window_errors_are_validation_responses(client, fields):
    body = dict(symbol='BENCH', date='2026-09-18', start='04:00', end='20:00')
    response = client.post('/api/sim/history/select', json=dict(body, **fields))
    assert response.status_code == 422
    assert response.json()['detail']


@pytest.mark.parametrize('date', ['2026-09-19', '2026-09-07'])
def test_weekend_holiday_selection_is_explicitly_empty_not_remapped(client, date):
    response = client.post('/api/sim/history/select', json=dict(
        symbol='  nonexistent ', date=date, start='04:00', end='20:00'))
    assert response.status_code == 200
    body = response.json()
    assert body['symbol'] == 'NONEXISTENT' and body['date'] == date
    assert body['download_status'] == 'missing' and body['trade_count'] == 0
    assert clock.status_payload()['second_max'] == 16 * 60 * 60


@pytest.mark.parametrize('date, hour', [('2026-03-06', 9), ('2026-03-09', 8),
                                      ('2025-10-31', 8), ('2025-11-03', 9)])
def test_market_window_offsets_across_dst_transitions(date, hour):
    spec = store.window('BENCH', date, '04:00', '20:00')
    assert datetime.fromtimestamp(spec['start_ts'], timezone.utc).hour == hour
    assert spec['end_ts'] - spec['start_ts'] == 16 * 60 * 60


def test_custom_window_after_default_close_and_reload(client):
    spec = dict(symbol='BENCH', date='2026-09-18', start='19:00', end='22:00')
    assert client.post('/api/sim/history/select', json=spec).status_code == 200
    clock.set_paused(True)
    clock.scrub_to_second(7200)
    assert clock.now_et().hour == 21
    assert client.post('/api/sim/history/select', json=spec).status_code == 200
    assert clock.now_et().hour == 21 and clock.is_paused()


def test_schema_initialized_once_and_recreated_database_invalidates(client, monkeypatch):
    from sim import history_schema
    calls = []
    original = sqlite3.connect
    def traced(*args, **kwargs):
        conn = original(*args, **kwargs)
        conn.set_trace_callback(calls.append)
        return conn
    monkeypatch.setattr(store.sqlite3, 'connect', traced)
    store.jobs()
    store.jobs()
    assert sum('CREATE TABLE IF NOT EXISTS jobs' in sql for sql in calls) == 1
    assert sum('PRAGMA journal_mode=WAL' in sql for sql in calls) == 1
    with store.connect() as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == history_schema.SCHEMA_VERSION
        assert conn.execute('PRAGMA busy_timeout').fetchone()[0] == 30000
    store.path().unlink()
    store.jobs()
    assert sum('CREATE TABLE IF NOT EXISTS jobs' in sql for sql in calls) == 2


@pytest.mark.parametrize('legacy', [False, True])
def test_recreated_database_with_reused_inode_and_no_birthtime_is_initialized(client, monkeypatch, legacy):
    database = store.path()
    stat = database.parent.stat()
    original_stat = type(database).stat
    def reused_stat(path, *args, **kwargs):
        if path == database:
            return SimpleNamespace(st_dev=stat.st_dev, st_ino=42)
        return original_stat(path, *args, **kwargs)
    monkeypatch.setattr(type(database), 'stat', reused_stat)
    assert store.jobs() == []  # Cache this identity before removing the file.
    database.unlink()
    if legacy:
        with sqlite3.connect(database) as conn:
            conn.execute('CREATE TABLE jobs (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            conn.execute('INSERT INTO jobs VALUES (?,?)', ('legacy', '{"id":"legacy"}'))
    assert store.jobs() == ([{'id': 'legacy'}] if legacy else [])
    with store.connect() as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM prints').fetchone()[0] == 0


@pytest.mark.parametrize('warm_cache', [False, True])
def test_unknown_schema_version_refuses_without_overwriting(client, warm_cache):
    if warm_cache:
        assert store.jobs() == []
    with sqlite3.connect(store.path()) as conn:
        conn.execute('PRAGMA user_version=999')
    response = client.get('/api/sim/history')
    assert response.status_code == 503
    with sqlite3.connect(store.path()) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 999


def test_worker_timeout_fails_with_cursor_preserved(client, monkeypatch):
    job = store.create(store.window('BENCH', '2026-09-18', '04:00', '09:30'), 'trades')
    class Gateway:
        closed = False
        async def open(self, symbol):
            await asyncio.sleep(1)
        def close(self):
            self.closed = True
    gateway = Gateway()
    monkeypatch.setattr(store, 'REQUEST_TIMEOUT', .01)
    result = asyncio.run(download.run(job['id'], gateway, threading.Event(), paced=False))
    assert result['status'] == 'failed' and result['cursor'] == job['cursor']
    # A timeout names the stage and the likely cause instead of a bare 'TimeoutError'.
    assert result['error'].startswith('IBKR did not answer within 0.01s while identifying BENCH')
    assert gateway.closed


def test_restart_does_not_claim_replay_loaded_and_durable_job_is_interrupted(client):
    spec = store.window('BENCH', '2026-09-18', '04:00', '09:30')
    job = store.create(spec, 'trades')
    store.save(dict(job, status='running', updated=time.time() - store.stale_after() - 1))
    playback.select(spec)
    playback.clear()  # Fresh process starts with no selection; archive survives.
    clock.reset_for_tests()
    listing = client.get('/api/sim/history').json()
    assert listing['selection'] is None
    assert listing['jobs'][0]['status'] == 'interrupted'
    assert listing['jobs'][0]['stale'] and listing['jobs'][0]['eta_seconds'] is None


def test_simultaneous_admission_has_one_owner_and_no_queued_orphan(client):
    from concurrent.futures import ThreadPoolExecutor
    barrier = threading.Barrier(2)
    def reserve(symbol):
        barrier.wait(timeout=2)
        try:
            return store.reserve_job(store.window(symbol, '2026-09-18', '04:00', '09:30'), 'trades')
        except ValueError as exc:
            return str(exc)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(reserve, ('RACEA', 'RACEB')))
    assert len([result for result in results if isinstance(result, dict)]) == 1
    assert len(store.jobs()) == 1 and store.jobs()[0]['status'] == 'running'
    assert any('pause it first' in result for result in results if isinstance(result, str))


# ── Exchange-calendar boundaries at the integration edge (#386) ───────────────
# The shared holiday table used to cover 2026 only, so historical selection in
# any other year picked exchange holidays as sessions and reported the prior
# close missing even when the true prior session was stored.

@pytest.mark.parametrize('now, expected', [
    ('2025-07-04T21:00', '2025-07-03'),  # the issue's exact case: Independence Day
    ('2025-07-07T10:00', '2025-07-03'),  # before Monday's close, back across Jul 4
    ('2025-01-09T21:00', '2025-01-08'),  # ad-hoc national day of mourning
    ('2025-04-18T21:00', '2025-04-17'),  # Good Friday
    ('2026-01-01T21:00', '2025-12-31'),  # cross-year
    ('2025-11-28T21:00', '2025-11-28'),  # day after Thanksgiving trades — do not over-close
])
def test_default_date_skips_holidays_outside_the_once_hardcoded_year(now, expected):
    assert store.default_date(datetime.fromisoformat(now).replace(tzinfo=store.ET)) == expected


def test_previous_close_reads_the_true_prior_session_across_a_holiday(client):
    """Prior close must not appear missing when the real prior session is stored."""
    import bars_store
    from sim import history_cache
    bars_store.write_payload(dict(symbol='HOLI', timeframe='1Min', bars=[
        # Thu 2025-07-03 15:59 ET is the prior session for Mon 2025-07-07.
        dict(t='2025-07-03T19:59:00Z', o=1, h=2, l=1, c=31.5, v=10),
        # Fri 2025-07-04 is an exchange holiday; this bar must never be chosen.
        dict(t='2025-07-04T19:59:00Z', o=1, h=2, l=1, c=99.9, v=10)]))
    assert history_cache.previous_close('HOLI', {'date': '2025-07-07'}) == 31.5


def test_previous_close_reads_the_prior_session_below_the_calendars_first_year(client):
    """The stored prior bar still wins when the walk leaves the vouched range.

    ``2015-01-02`` is inside the supported range but its prior session is not;
    the earlier fix returned None here and for every date before 2015-01-05,
    turning a working path into a miss even with the bar on disk (#386).
    """
    import bars_store
    from sim import history_cache
    bars_store.write_payload(dict(symbol='EDGE', timeframe='1Min', bars=[
        # Wed 2014-12-31 15:59 ET (EST, so 20:59Z) is the prior session.
        dict(t='2014-12-31T20:59:00Z', o=1, h=2, l=1, c=57.25, v=10)]))
    assert history_cache.previous_close('EDGE', {'date': '2015-01-02'}) == 57.25


def test_previous_close_still_answers_for_a_selection_older_than_the_calendar(client, caplog):
    """A pre-2015 archive keeps the weekday behaviour it had before the calendar."""
    import bars_store
    from sim import history_cache
    bars_store.write_payload(dict(symbol='OLDY', timeframe='1Min', bars=[
        # Wed 2014-06-04 15:59 ET (EDT, so 19:59Z).
        dict(t='2014-06-04T19:59:00Z', o=1, h=2, l=1, c=42.5, v=10)]))
    with caplog.at_level(logging.WARNING):
        assert history_cache.previous_close('OLDY', {'date': '2014-06-05'}) == 42.5
    assert 'outside the supported exchange calendar' in caplog.text


@pytest.mark.parametrize('path', ['/api/sim/history', '/api/sim/history/select'])
def test_an_out_of_range_selection_is_refused_at_the_operator_entry_point(client, path):
    """The date the operator typed is the one the refusal has to cover (#386)."""
    response = client.post(path, json=dict(
        symbol='BENCH', date='2014-06-05', start='04:00', end='20:00'))
    assert response.status_code == 422
    detail = response.json()['detail']
    assert '2014-06-05' in detail and '2015-2035' in detail
    # The operator reads this string; it must not describe Nova's own layout.
    assert '.py' not in detail and 'backend/' not in detail


def test_an_uncomputable_default_date_does_not_take_down_the_listing(client, monkeypatch, caplog):
    """One convenience field is not allowed to hide the operator's jobs (#386)."""
    store.create(store.window('BENCH', '2026-09-18', '04:00', '09:30'), 'trades')
    def refuse():
        raise ValueError('no calendar for this clock')
    monkeypatch.setattr(store, 'default_date', refuse)
    with caplog.at_level(logging.WARNING):
        response = client.get('/api/sim/history')
    assert response.status_code == 200
    body = response.json()
    assert body['default_date'] is None
    assert len(body['jobs']) == 1 and body['storage']
    assert 'Default replay date is unavailable' in caplog.text


def test_a_wall_clock_past_the_calendar_still_serves_the_listing(client, monkeypatch, caplog):
    """A slipped or future clock degrades the default date; it never 500s."""
    beyond, real = datetime(2036, 6, 2, 21, 0, tzinfo=store.ET), store.default_date
    monkeypatch.setattr(store, 'default_date', lambda: real(beyond))
    with caplog.at_level(logging.WARNING):
        response = client.get('/api/sim/history')
    assert response.status_code == 200
    assert response.json()['default_date'] == '2036-06-02'
    assert 'outside the supported exchange calendar' in caplog.text
