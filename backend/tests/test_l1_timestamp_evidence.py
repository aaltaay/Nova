"""Timestamp provenance uses native receipts, bounded arrival correlation and off-loop writes (#667)."""
from datetime import datetime, timezone
from types import SimpleNamespace as N

import pytest

from ibkr import l1_timestamp
from perf import l1_timestamps
from perf.store import PerfStore

BASE = 1_790_251_688.0


class Wrapper:
    def __init__(self):
        self.ticker = N(time=None, lastTimestamp=None, delayedLastTimestamp=None, ticks=[])
        self.subscriptions = N(get_ticker=lambda _id: self.ticker)
        self.lastTime = datetime.fromtimestamp(BASE, timezone.utc)

    def tickString(self, reqId, tickType, value):
        setattr(self.ticker, 'lastTimestamp' if tickType == 45 else 'delayedLastTimestamp',
                datetime.fromtimestamp(int(value), timezone.utc))

    def tickPrice(self, reqId, tickType, price, attrib):
        self.ticker.last = price

    def tickByTickAllLast(self, *args):
        pass


@pytest.fixture(autouse=True)
def evidence(monkeypatch):
    monkeypatch.setenv('NOVA_PERF', '1')
    l1_timestamps.reset_for_tests()
    l1_timestamp.reset_for_tests()
    yield
    l1_timestamps.reset_for_tests()
    l1_timestamp.reset_for_tests()


def test_unchanged_native_tick45_is_received_without_any_tickdata_and_seed_never_claims_it():
    wrapper = Wrapper()
    ib = N(wrapper=wrapper)
    assert l1_timestamp.install(ib)
    assert l1_timestamp.install(ib)
    wrapper.tickString(1, 45, str(int(BASE - 31)))
    wrapper.tickPrice(1, 4, 4.3, None)
    wrapper.ticker.time = wrapper.lastTime
    meta = l1_timestamp.provenance(wrapper.ticker, BASE, seed=False)
    assert wrapper.ticker.ticks == []
    assert meta['timestamp_receipt'] == {'tick_type': 45, 'stamp': BASE - 31,
                                       'received_at': BASE, 'with_price': True}
    assert meta['native_price_received'] is True
    assert l1_timestamp.provenance(wrapper.ticker, BASE, seed=True)['timestamp_receipt']['with_price'] is False
    wrapper.lastTime = datetime.fromtimestamp(BASE + 1, timezone.utc)
    wrapper.tickString(1, 45, str(int(BASE - 31)))  # unchanged value, a real new native receipt
    wrapper.ticker.time = wrapper.lastTime
    assert l1_timestamp.provenance(wrapper.ticker, BASE + 1, seed=False)['timestamp_receipt']['received_at'] == BASE + 1
    assert l1_timestamp.provenance(wrapper.ticker, BASE + 10, seed=False)['timestamp_receipt'] is None


def test_delayed88_and_receipts_are_scoped_to_an_ib_instance():
    first, second = Wrapper(), Wrapper()
    l1_timestamp.install(N(wrapper=first))
    l1_timestamp.install(N(wrapper=second))
    first.tickString(1, 88, str(int(BASE - 7)))
    first.tickPrice(1, 68, 4.3, None)
    first.ticker.time = first.lastTime
    meta = l1_timestamp.provenance(first.ticker, BASE, seed=False)
    assert meta['timestamp_receipt']['tick_type'] == 88
    second.tickPrice(1, 4, 4.3, None)
    second.ticker.time = second.lastTime
    newer = l1_timestamp.provenance(second.ticker, BASE, seed=False)
    assert newer['instance'] != meta['instance'] and newer['timestamp_receipt'] is None


def test_reusing_an_ib_wrapper_after_ready_invalidates_receipts_and_correlation_identity():
    generation = [1]
    wrapper = Wrapper()
    l1_timestamp.install(N(wrapper=wrapper), session=lambda: generation[0])
    wrapper.tickString(1, 45, str(int(BASE - 31)))
    wrapper.tickPrice(1, 4, 4.3, None)
    wrapper.ticker.time = wrapper.lastTime
    prior = l1_timestamp.provenance(wrapper.ticker, BASE, seed=False)
    generation[0] = 2  # same IB and ticker may survive a data-kept reconnect
    stale = l1_timestamp.provenance(wrapper.ticker, BASE + .1, seed=False)
    assert stale['instance'] is None and stale['timestamp_receipt'] is None
    assert stale['native_price_received'] is False
    wrapper.lastTime = datetime.fromtimestamp(BASE + .2, timezone.utc)
    wrapper.tickPrice(1, 4, 4.4, None)
    wrapper.ticker.time = wrapper.lastTime
    newer = l1_timestamp.provenance(wrapper.ticker, BASE + .2, seed=False)
    assert newer['instance'] != prior['instance'] and newer['timestamp_receipt'] is None


def test_correlates_before_and_after_same_price_prints_but_never_other_instance_or_unreported():
    meta = {'instance': 'one', 'timestamp_receipt': None, 'native_price_received': True}
    l1_timestamps.note_price('PFSA', 4.3, BASE - 31, BASE, metadata=meta, seed=False, quote_quality=None)
    for instance, at, price, price_ok in [('one', BASE - .2, 4.3, True), ('one', BASE + .4, 4.3, True),
                                         ('two', BASE + .1, 4.3, True), ('one', BASE, 4.4, True),
                                         ('one', BASE, 4.3, False)]:
        l1_timestamps.note_tape('PFSA', price, int(at), at, instance=instance, price_ok=price_ok)
    rows = []
    l1_timestamps.flush(rows.append, now=BASE + 3)
    assert len(rows) == 1
    assert [round(p['delta_sec'], 1) for p in rows[0]['tape_candidates']] == [-.2, .4]
    assert rows[0]['price_ts'] == BASE - 31 and rows[0]['arrival_ts'] == BASE
    assert rows[0]['kind'] == 'l1_timestamp' and rows[0]['schema_version'] == 1


def test_timestamp_file_cap_is_separate_from_perf_samples_and_read_refuses_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr('perf.store.time.time', lambda: BASE)
    store = PerfStore(tmp_path)
    store.put_timestamp({'schema_version': 1, 'kind': 'l1_timestamp', 'arrival_ts': BASE})
    store.drain()
    monkeypatch.setattr('perf.store.PERF_L1_TIMESTAMP_DAY_MAX_MB', 0)
    store.put_timestamp({'schema_version': 1, 'kind': 'l1_timestamp', 'arrival_ts': BASE + 1})
    store.put({'schema_version': 1, 'kind': 'sample', 'ts': BASE})
    store.drain()
    assert store.timestamp_files_dropped == 1
    assert len(list(store.root.glob('*.jsonl'))) == 1
    path = next((store.root / 'l1_timestamps').glob('*.jsonl'))
    assert len(list(l1_timestamps.read_file(path))) == 1
    path.write_text('{"schema_version":2}\n')
    with pytest.raises(ValueError, match='schema'):
        list(l1_timestamps.read_file(path))


def test_queue_rate_and_pending_bounds_are_counted_and_off_switch_collects_nothing(monkeypatch):
    import queue
    from perf import counters

    counters.reset_for_tests()
    monkeypatch.setattr(l1_timestamps, '_prices', queue.Queue(maxsize=1))
    monkeypatch.setattr(l1_timestamps, 'PERF_L1_TIMESTAMP_PRICES_PER_SEC', 2)
    monkeypatch.setattr(l1_timestamps.time, 'monotonic', lambda: 100.0)
    metadata = {'instance': 'one', 'timestamp_receipt': None, 'native_price_received': False}
    for _ in range(3):
        l1_timestamps.note_price('PFSA', 4.3, BASE, BASE, metadata=metadata, seed=True, quote_quality=None)
    assert counters.read()['l1_timestamp.queue_dropped'] == 1
    assert counters.read()['l1_timestamp.rate_dropped'] == 1
    rows = []
    l1_timestamps.flush(rows.append, now=BASE + 3)
    assert len(rows) == 1 and rows[0]['seed'] is True
    monkeypatch.setenv('NOVA_PERF', '0')
    l1_timestamps.note_price('PFSA', 5, BASE, BASE, metadata=metadata, seed=False, quote_quality=None)
    l1_timestamps.flush(rows.append, now=BASE + 3)
    assert len(rows) == 1


def test_a_full_shared_writer_queue_counts_timestamp_loss_once_but_none_sink_succeeds(tmp_path):
    from perf import counters

    counters.reset_for_tests()
    store = PerfStore(tmp_path)
    for _ in range(store._queue.maxsize):
        store.put({'kind': 'sample', 'ts': BASE})
    metadata = {'instance': 'one', 'timestamp_receipt': None, 'native_price_received': False}
    l1_timestamps.note_price('PFSA', 4.3, BASE, BASE, metadata=metadata, seed=False, quote_quality=None)
    l1_timestamps.flush(store.put_timestamp, now=BASE + 3)
    assert store.write_dropped == 1
    assert counters.read()['l1_timestamp.queue_dropped'] == 1
    l1_timestamps.flush(store.put_timestamp, now=BASE + 4)
    assert store.write_dropped == 1 and counters.read()['l1_timestamp.queue_dropped'] == 1
    rows = []
    l1_timestamps.note_price('PFSA', 4.3, BASE + 4, BASE + 4, metadata=metadata, seed=False, quote_quality=None)
    l1_timestamps.flush(rows.append, now=BASE + 7)  # list.append returns None on success
    assert len(rows) == 1 and counters.read()['l1_timestamp.queue_dropped'] == 1


@pytest.mark.parametrize('timestamp_type,price_type', [(45, 4), (88, 68)])
@pytest.mark.parametrize('first_timestamp', [False, True])
def test_native_wire_receipts_survive_tape_hook_order_repeated_values_and_a_new_session(
    first_timestamp, timestamp_type, price_type,
):
    from ib_async import IB, Stock
    from ibkr import tape_exchange_time

    ib = IB()
    contract = Stock('PFSA', 'SMART', 'USD')
    contract.conId = 42
    ib.client.getReqId = lambda: 123
    ib.client.reqMktData = lambda *_args: None
    ticker = ib.reqMktData(contract)
    generation = [1]
    def session():
        return generation[0]

    if first_timestamp:
        l1_timestamp.install(ib, session=session)
        tape_exchange_time.install(ib)
    else:
        tape_exchange_time.install(ib)
        l1_timestamp.install(ib, session=session)
    handler = ib.client.decoder.handlers[46]
    hook = ib.wrapper.tickString
    assert l1_timestamp.install(ib, session=session)
    assert ib.client.decoder.handlers[46] is handler and ib.wrapper.tickString is hook

    def dispatch(at):
        ib.wrapper.lastTime = datetime.fromtimestamp(at, timezone.utc)
        ib.client.decoder.interpret(['46', '2', '123', str(timestamp_type), str(int(BASE - 31))])
        ib.client.decoder.interpret(['1', '6', '123', str(price_type), '4.3', '100', '0'])
        ib.wrapper.tcpDataProcessed()
        return l1_timestamp.provenance(ticker, at, seed=False)

    first = dispatch(BASE)
    assert first['native_price_received'] is True
    assert first['timestamp_receipt'] == {'tick_type': timestamp_type, 'stamp': BASE - 31,
                                          'received_at': BASE, 'with_price': True}
    assert not any(t.tickType in (45, 88) for t in ticker.ticks)
    repeated = dispatch(BASE + .25)
    assert repeated['timestamp_receipt']['received_at'] == BASE + .25
    assert repeated['timestamp_receipt']['stamp'] == BASE - 31
    ib.client.decoder.interpret(['99', '123', '2', str(int(BASE - 1)), '4.3', '100', '0', 'NASDAQ', ''])
    assert tape_exchange_time.exchange_second(ticker.tickByTicks[-1]) == int(BASE - 1)
    assert ticker.tickByTicks[-1].time.timestamp() == BASE + .25
    assert l1_timestamp.instance(ticker) == first['instance']
    generation[0] = 2
    assert l1_timestamp.provenance(ticker, BASE + .3, seed=False)['timestamp_receipt'] is None
    assert l1_timestamp.instance(ticker) is None
    renewed = dispatch(BASE + .5)
    assert renewed['instance'] != first['instance']
    assert renewed['timestamp_receipt']['with_price'] is True


def test_decoder_rebind_failure_preserves_native_handlers_and_can_retry(monkeypatch, caplog):
    from ib_async import IB

    ib = IB()
    wrapper, decoder = ib.wrapper, ib.client.decoder
    originals = (wrapper.tickString, wrapper.priceSizeTick, wrapper.tickByTickAllLast, decoder.handlers[46])
    native_wrap = decoder.wrap

    def failed_wrap(*_args):
        raise RuntimeError('cannot bind')

    monkeypatch.setattr(decoder, 'wrap', failed_wrap)
    assert l1_timestamp.install(ib) is False
    assert (wrapper.tickString, wrapper.priceSizeTick, wrapper.tickByTickAllLast, decoder.handlers[46]) == originals
    assert 'native decoder receipt hook unavailable' in caplog.text
    monkeypatch.setattr(decoder, 'wrap', native_wrap)
    assert l1_timestamp.install(ib) is True
    handler = decoder.handlers[46]
    assert l1_timestamp.install(ib) is True and decoder.handlers[46] is handler
