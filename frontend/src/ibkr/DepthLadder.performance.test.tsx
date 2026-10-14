/** @vitest-environment jsdom */
import { act, Profiler } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TopOfBookProvider } from '../hotkeys/TopOfBookContext';
import { viewLockReason, viewStampFor } from '../market_view';
import { resetViewRegistryForTests } from '../market_view/viewRegistry';
import { resetPerfCountersForTests, takeCounters } from '../perf/perfCounters';
import { DepthLadder } from './DepthLadder';
import type { DepthMarker } from './depthMarkers';
import type { LuldView } from './luld';

const SYMBOL = 'FIXTURE';
const NOW = 1_792_000_000;
const UPDATES = 200;
const markers: DepthMarker[] = [
  { id: 'entry', price: 10, label: 'ENTRY', color: '#aaa', working: false, rests: 'bid', tip: 'Entry plan' },
  { id: 'stop', price: 9.95, label: 'STOP', color: '#f55', working: true, rests: 'bid', tip: 'Working stop' },
  { id: 'target', price: 10.06, label: 'TARGET', color: '#5f5', working: false, rests: 'ask', tip: 'Target plan' },
];

class FakeSocket {
  static instances: FakeSocket[] = [];
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  constructor(readonly url: string) { FakeSocket.instances.push(this); }
  close() { this.onclose?.(); }
}

function book(seq: number, bid = 10) {
  return {
    type: 'book', symbol: SYMBOL, seq, at: NOW + seq / 1000, sent: Date.now() / 1000,
    data: {
      bids: Array.from({ length: 10 }, (_, i) => ({
        price: Number((bid - i / 100).toFixed(2)), size: i === 7 ? 500 + seq : 1000, mm: 'TEST',
      })),
      asks: Array.from({ length: 10 }, (_, i) => ({
        price: Number((bid + (i + 1) / 100).toFixed(2)), size: 1000, mm: 'TEST',
      })),
      l1_fallback: false,
    },
  };
}

function watch(seq = 1, pulled = 5800) {
  return {
    type: 'book_watch', symbol: SYMBOL,
    data: {
      schema_version: 1, now: NOW, reset: true, seq, watching: true, reason: null, window_sec: 60,
      sides: {
        bid: { pulled_shares: pulled, filled_shares: 100, large_pulls: 1 },
        ask: { pulled_shares: 0, filled_shares: 400, large_pulls: 0 },
      },
      drops: [{ seq, ts: NOW, side: 'bid', price: 9.98, pulled, filled: 0,
        outcome: 'pulled', large_pull: true, on_approach: false }],
    },
  };
}

function luld(upper = 10.08): LuldView {
  return {
    schema_version: 1, symbol: SYMBOL, source: 'live', state: 'bands', exact: true,
    lower: 9.92, upper, reference: 10, reference_since: NOW - 20,
    reference_source: 'open', reference_words: 'the opening print', percent: '10%',
    prev_close: 10, tier: 2, tier_text: 'fixture Tier 2', tier_sure: true, spread: null,
    limit: null, straddle: null, anchor: { kind: 'open', ts: NOW - 20, price: 10 },
    halted_since: null, watching_since: NOW - 3600, warm_until: null, gap: null,
    last: 10, distance: { down_pct: -0.008, up_pct: 0.008 }, near: null, reason: null,
    history: [], note: "Nova's calculation", rules: 'Fixture published-rule input', track: null,
    as_of: NOW, text: 'Fixture bands', watching: true,
  };
}

describe('actual depth ladder performance fixture (#797)', () => {
  let container: HTMLDivElement;
  let root: Root;
  let durations: number[];

  function render(active = true) {
    act(() => root.render(
      <TopOfBookProvider>
        <Profiler id="depth-fixture" onRender={(_id, _phase, actualDuration) => durations.push(actualDuration)}>
          <DepthLadder symbol={SYMBOL} uiActive={active} markers={markers} traderTab />
        </Profiler>
      </TopOfBookProvider>,
    ));
  }

  function send(frame: unknown) {
    act(() => FakeSocket.instances[0].onmessage?.({ data: JSON.stringify(frame) }));
  }

  function prime() {
    render();
    send({ type: 'subscribed', symbol: SYMBOL, instance: 'fixture-instance' });
    send(book(1));
    send(watch());
    send({ type: 'luld', symbol: SYMBOL, data: luld() });
  }

  function assertAnnotations() {
    for (const id of ['entry', 'stop', 'target']) {
      expect(container.querySelector(`[data-testid="l2-marker-${id}"]`)).not.toBeNull();
    }
    expect(container.querySelector('[data-testid="l2-marker-stop"]')?.className).toContain('--working');
    expect(container.querySelector('[data-testid="l2-pullmark-pulled"]')?.textContent).toContain('5,800');
    expect(container.querySelector('[data-testid="l2-pulls-bid"]')?.textContent).toContain('5.8K');
    expect(container.querySelector('[data-testid="l2-luld-bid"]')?.textContent).toContain('9.92');
    expect(container.querySelector('[data-testid="l2-luld-ask"]')?.textContent).toContain('10.08');
  }

  beforeEach(() => {
    FakeSocket.instances = [];
    durations = [];
    vi.stubGlobal('WebSocket', FakeSocket);
    // React's timing clock remains real. Only the fixture's market/aging clock and timers are controlled.
    vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] });
    vi.setSystemTime(NOW * 1000);
    resetViewRegistryForTests();
    resetPerfCountersForTests();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    resetViewRegistryForTests();
    resetPerfCountersForTests();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('measures active book work with plan, book-watch and LULD, and stamps every newest book', () => {
    prime();
    assertAnnotations();
    durations = [];
    takeCounters();
    const formatting = vi.spyOn(Number.prototype, 'toLocaleString');
    for (let i = 2; i <= UPDATES + 1; i += 1) {
      send(book(i));
      expect(viewStampFor(SYMBOL, Date.now()).book).toEqual({ seq: i, at: NOW + i / 1000, bid: 10, ask: 10.01 });
      expect(viewLockReason(SYMBOL)).toBeNull();
      expect(container.querySelectorAll('.das-l2-side--bid .das-l2-row:not(.das-l2-row--luld)')[7].textContent).toContain(String(500 + i));
    }
    const uncachedLocaleCalls = formatting.mock.calls.length;
    const renders = takeCounters().renders.DepthLadder;
    const sorted = [...durations].sort((a, b) => a - b);
    console.info('DEPTH_FIXTURE', JSON.stringify({
      updates: UPDATES, commits: durations.length, renders, uncachedLocaleCalls,
      totalRenderMs: durations.reduce((sum, ms) => sum + ms, 0),
      p95RenderMs: sorted[Math.ceil(sorted.length * 0.95) - 1],
      maxRenderMs: sorted.at(-1), environment: 'React development build, jsdom, synthetic books',
    }));
    expect(renders).toBe(UPDATES);
    expect(durations).toHaveLength(UPDATES);
    expect(uncachedLocaleCalls).toBe(0);
    assertAnnotations();
  });

  it('beats cost no paint, hidden updates resume at the newest sequence, and annotations still update', () => {
    prime();
    takeCounters();
    durations = [];
    for (let i = 0; i < 100; i += 1) {
      send({ type: 'beat', symbol: SYMBOL, seq: 1, now: Date.now() / 1000 });
    }
    expect(takeCounters().renders.DepthLadder ?? 0).toBe(0);
    expect(durations).toHaveLength(0);
    expect(viewLockReason(SYMBOL)).toBeNull();

    render(false);
    takeCounters();
    durations = [];
    for (let i = 2; i <= 50; i += 1) send(book(i, 10.02));
    expect(takeCounters().renders.DepthLadder ?? 0).toBe(0);
    expect(durations).toHaveLength(0);
    expect(viewStampFor(SYMBOL, Date.now()).book?.seq).toBe(1);
    render(true);
    expect(viewStampFor(SYMBOL, Date.now()).book).toEqual({ seq: 50, at: NOW + 0.05, bid: 10.02, ask: 10.03 });
    expect(viewLockReason(SYMBOL)).toBeNull();
    expect(container.querySelector('.das-l2-bbo')?.textContent).toContain('10.02 × 10.03');
    expect(FakeSocket.instances).toHaveLength(1);
    assertAnnotations();

    send(watch(2, 7200));
    send({ type: 'luld', symbol: SYMBOL, data: luld(10.09) });
    expect(container.querySelector('[data-testid="l2-pullmark-pulled"]')?.textContent).toContain('7,200');
    expect(container.querySelector('[data-testid="l2-luld-ask"]')?.textContent).toContain('10.09');
    render();
    send(book(51, 10.02));
    expect(viewStampFor(SYMBOL, Date.now()).book?.seq).toBe(51);
  });

  it('keeps distinct coincident annotations keyed without a React list warning', () => {
    const errors = vi.spyOn(console, 'error');
    act(() => root.render(
      <DepthLadder symbol={SYMBOL} markers={[
        ...markers, { ...markers[0], id: 'entry-other', label: 'OTHER ENTRY' },
        { ...markers[1], id: 'stop-other', label: 'OTHER STOP' },
      ]} />,
    ));
    send(book(1));
    send(watch());
    send({ type: 'luld', symbol: SYMBOL, data: luld() });
    for (const id of ['entry', 'entry-other', 'stop', 'stop-other', 'target']) {
      expect(container.querySelectorAll(`[data-testid="l2-marker-${id}"]`)).toHaveLength(1);
    }
    for (const [message] of errors.mock.calls) expect(String(message)).not.toContain('unique "key"');
  });

  it('a newer freshness beat never claims its undrawn book was shown, and a slow frame stays locked', () => {
    prime();
    takeCounters();
    send({ type: 'beat', symbol: SYMBOL, seq: 2, now: Date.now() / 1000 });
    expect(takeCounters().renders.DepthLadder ?? 0).toBe(0);
    expect(viewStampFor(SYMBOL, Date.now()).book?.seq).toBe(1);
    act(() => vi.advanceTimersByTime(600));
    expect(viewLockReason(SYMBOL)).not.toBeNull();
    expect(viewStampFor(SYMBOL, Date.now()).book?.seq).toBe(1);
    send(book(2));
    expect(viewStampFor(SYMBOL, Date.now()).book?.seq).toBe(2);
    expect(viewLockReason(SYMBOL)).toBeNull();
    send({ ...book(3), sent: Date.now() / 1000 - 2 });
    expect(viewStampFor(SYMBOL, Date.now()).book?.seq).toBe(3);
    expect(viewLockReason(SYMBOL)).toContain('took 2.0 s to arrive');
  });
});
