import asyncio
import threading

import pytest

from sim import history_store as store
from sim.history_download import page, run


@pytest.fixture
def job(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SIM_HISTORY_DIR", str(tmp_path))
    return store.create(store.window("IMCC", "2026-09-18", "04:00", "09:30"), "trades")


def trade(ts):
    return dict(ts=ts, price=10, size=2, symbol="IMCC", exchange="ARCA", conditions="")


def test_identical_prints_full_second_and_atomic_resume(job):
    cursor = job["cursor"]
    rows, following, complete = page([trade(cursor)] * 1003, cursor, job["end_ts"])
    assert len(rows) == 1003 and following == cursor + 1 and not complete
    store.commit_page(job["id"], cursor, rows, following, complete)
    assert len(store.read_prints(job["id"])) == 1003
    with pytest.raises(ValueError, match="cursor changed"):
        store.commit_page(job["id"], cursor, rows, following, complete)
    assert store.get(job["id"])["volume"] == 2006


def test_range_excludes_end_and_rejects_overlapping_page(job):
    a, b = job["cursor"], job["end_ts"]
    assert page([trade(b - 1), trade(b)], a, b) == ([trade(b - 1)], b, True)
    with pytest.raises(ValueError, match="overlapping"):
        page([trade(a - 1)], a, b)
    with pytest.raises(ValueError, match="empty page"):
        page([], a, b)
    assert page([], b, b) == ([], b, True)


def test_timezone_and_validation():
    summer = store.window("F", "2026-09-18", "04:00", "09:30")
    winter = store.window("SPY", "2026-01-16", "04:00", "09:30")
    from datetime import datetime, timezone
    assert datetime.fromtimestamp(summer["start_ts"], timezone.utc).hour == 8
    assert datetime.fromtimestamp(winter["start_ts"], timezone.utc).hour == 9
    with pytest.raises(ValueError):
        store.window("../bad", "2026-09-18", "04:00", "09:30")


def test_interrupted_download_resumes_at_next_second(job):
    class Gateway:
        calls = []
        fail = True
        async def open(self, symbol):
            return {"conId": 12}
        async def trades(self, cursor):
            self.calls.append(cursor)
            if cursor == job["cursor"]:
                return [trade(cursor)] * 2
            if self.fail:
                raise TimeoutError("interrupted")
            return [trade(job["end_ts"])]
        def close(self):
            pass
    g = Gateway()
    result = asyncio.run(run(job["id"], g, threading.Event(), paced=False))
    assert result["status"] == "failed" and result["count"] == 2
    g.fail = False
    result = asyncio.run(run(job["id"], g, threading.Event(), paced=False))
    assert result["status"] == "complete" and result["count"] == 2
    assert g.calls == [job["cursor"], job["cursor"] + 1, job["cursor"] + 1]


def test_pause_during_inflight_page_preserves_checkpoint(job):
    class Gateway:
        async def open(self, symbol):
            return {"conId": 12}
        async def trades(self, cursor):
            store.request_pause(job["id"])
            return [trade(cursor), trade(cursor)]
        def close(self):
            pass
    result = asyncio.run(run(job["id"], Gateway(), threading.Event(), paced=False))
    assert result["status"] == "paused"
    assert result["count"] == 2
    assert result["cursor"] == job["cursor"] + 1


def test_contract_change_and_nonfinite_prints_fail_closed(job):
    job["contract"] = {"conId": 12}
    store.save(job)
    class Gateway:
        async def open(self, symbol):
            return {"conId": 13}
        def close(self):
            pass
    result = asyncio.run(run(job["id"], Gateway(), threading.Event(), paced=False))
    assert result["status"] == "failed" and result["count"] == 0
    with pytest.raises(ValueError, match="Invalid"):
        page([dict(trade(job["cursor"]), size=float('nan'))], job["cursor"],job["end_ts"])


def test_begin_run_keeps_a_pause_requested_before_the_worker_starts(job):
    store.claim(job["id"])
    store.request_pause(job["id"])
    assert store.begin_run(job["id"])["status"] == "pause_requested"

    class Gateway:
        async def open(self, symbol):
            return {"conId": 12}
        async def trades(self, cursor):
            raise AssertionError("paused job must not request another page")
        def close(self):
            pass
    assert asyncio.run(run(job["id"], Gateway(), threading.Event(), paced=False))["status"] == "paused"


def test_bars_job_persists_candles_in_archive_and_chart_store(tmp_path, monkeypatch):
    import bars_store
    from archive import db
    from datetime import datetime, timezone
    monkeypatch.setenv("NOVA_SIM_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setattr(db, "cache_dir", lambda: tmp_path)
    db.init_db()
    spec = store.window("F", "2026-09-18", "04:00", "04:10")
    bars_job = store.create(spec, "bars")
    rows = [dict(t=datetime.fromtimestamp(spec["start_ts"] + 60 * i, timezone.utc).isoformat(),
                 o=1, h=2, l=1, c=2, v=10) for i in range(10)]

    class Gateway:
        async def open(self, symbol):
            return {"conId": 9}
        async def bars(self, job):
            return rows
        def close(self):
            pass
    result = asyncio.run(run(bars_job["id"], Gateway(), threading.Event(), paced=False))
    assert result["status"] == "complete" and result["count"] == 10 and result["volume"] == 100
    assert len(store.read_candles("F", spec["start_ts"], spec["end_ts"])) == 10
    assert len(bars_store.read("F", "1Min", 100)["bars"]) == 10
    assert len(bars_store.read("F", "5Min", 100)["bars"]) == 2


def test_gateway_tries_live_then_paper_port(monkeypatch):
    from ibkr.replay_history_gateway import candidate_ports
    monkeypatch.setenv("IBKR_LIVE_PORT", "4001")
    monkeypatch.setenv("IBKR_PAPER_PORT", "4002")
    assert candidate_ports() == [4001, 4002]
    monkeypatch.setenv("IBKR_PAPER_PORT", "4001")
    assert candidate_ports() == [4001]


def test_both_ports_dark_names_the_shared_unreachable_prefix(monkeypatch):
    """The Sim tab prompt auto-retries on exactly this prefix once Gateway is back."""
    import ib_async

    from constants_sim import SIM_HISTORY_GATEWAY_UNREACHABLE
    from ibkr.replay_history_gateway import ReplayHistoryGateway

    class RefusingIB:
        RaiseRequestErrors = False

        async def connectAsync(self, *args, **kwargs):
            raise ConnectionRefusedError("[WinError 1225] refused")

        def disconnect(self):
            pass

    monkeypatch.setattr(ib_async, "IB", RefusingIB)
    monkeypatch.setenv("IBKR_LIVE_PORT", "4001")
    monkeypatch.setenv("IBKR_PAPER_PORT", "4002")
    with pytest.raises(ConnectionError) as refused:
        asyncio.run(ReplayHistoryGateway().open("IMCC"))
    assert str(refused.value).startswith(SIM_HISTORY_GATEWAY_UNREACHABLE)
    assert "4001" in str(refused.value) and "4002" in str(refused.value)


@pytest.mark.parametrize("now, expected", [
    ("2026-09-19T12:00", "2026-09-18"),  # Saturday -> Friday
    ("2026-09-18T19:59", "2026-09-17"),  # Friday before the default close
    ("2026-09-18T20:00", "2026-09-18"),
    ("2026-09-08T10:00", "2026-09-04"),  # Tuesday after Labor Day
])
def test_default_date_is_latest_completed_trading_day(now, expected):
    from datetime import datetime
    assert store.default_date(datetime.fromisoformat(now).replace(tzinfo=store.ET)) == expected


def test_empty_page_fails_resumably_without_advancing_committed_cursor(job):
    class Gateway:
        calls = []
        empty = True
        async def open(self, symbol):
            return {'conId': 12}
        async def trades(self, cursor):
            self.calls.append(cursor)
            if cursor == job['cursor']:
                return [trade(cursor), trade(cursor)]
            return [] if self.empty else [trade(job['end_ts'])]
        def close(self):
            pass
    gateway = Gateway()
    failed = asyncio.run(run(job['id'], gateway, threading.Event(), paced=False))
    assert failed['status'] == 'failed'
    assert failed['cursor'] == job['cursor'] + 1 and failed['count'] == 2
    assert 'empty page' in failed['error']
    gateway.empty = False
    resumed = asyncio.run(run(job['id'], gateway, threading.Event(), paced=False))
    assert resumed['status'] == 'complete' and resumed['count'] == 2
    assert gateway.calls == [job['cursor'], job['cursor'] + 1, job['cursor'] + 1]


def test_eta_uses_this_run_coverage_and_never_invents_progress(job, monkeypatch):
    from sim.history_progress import progress
    queued = progress(job, now=job['updated'])
    assert queued['progress_pct'] == 0 and queued['eta_seconds'] is None
    # Progress is covered time, and the ETA extrapolates coverage gained this run.
    current = dict(job, started=100, updated=120, run_cursor=job['cursor'], run_covered=0,
                   ranges=[[job['start_ts'], job['cursor'] + 1980]],
                   cursor=job['cursor'] + 1980, status='running')
    result = progress(current, now=130)
    assert result['progress_pct'] == 10 and result['eta_seconds'] == 180
    assert result['downloaded_through'] == current['cursor'] and result['age_seconds'] == 10
    assert result['covered_seconds'] == 1980 and result['coverage'] == current['ranges']
    # A job saved before coverage ranges reads its cursor as one contiguous range.
    legacy = {k: v for k, v in current.items() if k != 'ranges'}
    assert progress(legacy, now=130)['progress_pct'] == 10
    assert progress(current, now=500)['stale']
    assert progress(current, now=500)['eta_seconds'] is None
    for status in ('queued', 'paused', 'failed', 'complete', 'interrupted'):
        assert progress(dict(current, status=status), now=130)['eta_seconds'] is None
    monkeypatch.setattr(store.time, 'time', lambda: 1000)
    store.save(dict(current, status='paused'))
    resumed = store.begin_run(job['id'])
    assert resumed['started'] == 1000 and resumed['run_cursor'] == current['cursor']
    assert resumed['run_covered'] == 1980
    assert progress(resumed, now=1001)['eta_seconds'] is None


def test_a_gateway_that_never_answers_says_so_instead_of_a_bare_timeout(job, monkeypatch):
    """Seen live 2026-09-21 01:30 ET: 4002 accepted the socket, qualifyContracts hung 45 s."""
    from constants_sim import SIM_HISTORY_GATEWAY_NOT_ANSWERING
    monkeypatch.setattr(store, "REQUEST_TIMEOUT", 0.05)

    class Silent:
        async def open(self, symbol):
            await asyncio.sleep(10)

        def close(self):
            pass

    result = asyncio.run(run(job["id"], Silent(), threading.Event(), paced=False))
    assert result["status"] == "failed"
    assert result["error"].startswith(SIM_HISTORY_GATEWAY_NOT_ANSWERING)
    assert "identifying IMCC" in result["error"] and "Gateway window" in result["error"]
