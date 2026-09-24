/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  FOCUS_HEARTBEAT_MS,
  FOCUS_INPUT_REPORT_MIN_MS,
  FOCUS_SCHEMA_VERSION,
  FOCUS_SETTLE_MS,
} from '../constantGroups/focus';
import {
  buildFocusReport,
  EMPTY_FOCUS_VIEW,
  resetFocusReporterForTests,
  setFocusView,
  startFocusReporter,
  type FocusDocument,
  type FocusView,
  type FocusWindow,
} from './focusReporter';

type Handler = (...args: unknown[]) => void;

function target() {
  const handlers = new Map<string, Handler[]>();
  return {
    addEventListener: (name: string, fn: Handler) => handlers.set(name, [...(handlers.get(name) ?? []), fn]),
    removeEventListener: (name: string, fn: Handler) =>
      handlers.set(name, (handlers.get(name) ?? []).filter((h) => h !== fn)),
    fire: (name: string) => (handlers.get(name) ?? []).forEach((h) => h()),
  };
}

function fakeWin(search = '', desktop = true) {
  return {
    ...target(),
    location: { href: `http://127.0.0.1:5173/${search}`, search },
    novaDesktop: desktop ? { isDesktop: true } : undefined,
  };
}

function fakeDoc(focused = true) {
  return { ...target(), hasFocus: () => focused, visibilityState: 'visible' as DocumentVisibilityState };
}

const GCTK: FocusView = {
  page: 'trader',
  tab: null,
  symbol: 'GCTK',
  symbolSource: 'trader_tab',
  traderTabs: ['GCTK', 'PFSA'],
};

function start(win = fakeWin(), doc = fakeDoc()) {
  let clock = 1_790_000_000_000;
  const post = vi.fn(async (_body: string) => ({ ok: true, status: 200 }));
  const stop = startFocusReporter({
    win: win as unknown as FocusWindow,
    doc: doc as unknown as FocusDocument,
    now: () => clock,
    post,
  });
  const bodies = () => post.mock.calls.map(([body]) => JSON.parse(body));
  return { post, stop, bodies, advance: (ms: number) => (clock += ms), win, doc };
}

afterEach(() => {
  resetFocusReporterForTests();
  vi.useRealTimers();
});

describe('focus report', () => {
  it('has the wire shape the backend validates', () => {
    const report = buildFocusReport({
      windowId: 'main',
      role: 'main',
      instanceId: 'abc',
      focused: true,
      visible: true,
      view: GCTK,
      lastInputMs: 1_790_000_000_123,
      reason: 'focus',
      uiTag: 'v993',
    });
    expect(report).toEqual({
      schema_version: FOCUS_SCHEMA_VERSION,
      role: 'main',
      window_id: 'main',
      instance_id: 'abc',
      focused: true,
      visible: true,
      page: 'trader',
      tab: null,
      symbol: 'GCTK',
      symbol_source: 'trader_tab',
      trader_tabs: ['GCTK', 'PFSA'],
      last_input_ts: 1_790_000_000.123,
      reason: 'focus',
      ui_tag: 'v993',
    });
  });

  it('reports on start, then once when the view settles', async () => {
    vi.useFakeTimers();
    const r = start();
    expect(r.bodies()[0]).toMatchObject({ reason: 'start', page: null, role: 'main', focused: true });
    await vi.advanceTimersByTimeAsync(0);
    setFocusView({ ...GCTK, symbol: 'PFSA' });
    setFocusView(GCTK); // same render burst: one post with the settled view
    await vi.advanceTimersByTimeAsync(FOCUS_SETTLE_MS);
    expect(r.post).toHaveBeenCalledTimes(2);
    expect(r.bodies()[1]).toMatchObject({ reason: 'page', symbol: 'GCTK', page: 'trader' });
    setFocusView(GCTK); // unchanged: nothing sent
    await vi.advanceTimersByTimeAsync(FOCUS_SETTLE_MS);
    expect(r.post).toHaveBeenCalledTimes(2);
  });

  it('reports focus changes at once and heartbeats while open', async () => {
    vi.useFakeTimers();
    const r = start();
    await vi.advanceTimersByTimeAsync(0);
    r.win.fire('blur');
    await vi.advanceTimersByTimeAsync(0);
    expect(r.bodies()[1].reason).toBe('blur');
    await vi.advanceTimersByTimeAsync(FOCUS_HEARTBEAT_MS);
    expect(r.bodies().at(-1)?.reason).toBe('heartbeat');
  });

  it('stamps the last input and reports it at most every few seconds', async () => {
    vi.useFakeTimers();
    const r = start();
    await vi.advanceTimersByTimeAsync(0);
    r.advance(FOCUS_INPUT_REPORT_MIN_MS);
    r.win.fire('pointerdown');
    await vi.advanceTimersByTimeAsync(0);
    expect(r.bodies()[1].reason).toBe('input');
    expect(r.bodies()[1].last_input_ts).not.toBeNull();
    r.win.fire('keydown'); // too soon: rides on the next report
    await vi.advanceTimersByTimeAsync(0);
    expect(r.post).toHaveBeenCalledTimes(2);
  });

  it('waits for the post in flight and then sends the change', async () => {
    vi.useFakeTimers();
    let release: (v: { ok: boolean; status: number }) => void = () => {};
    const post = vi.fn(() => new Promise<{ ok: boolean; status: number }>((resolve) => (release = resolve)));
    startFocusReporter({
      win: fakeWin() as unknown as FocusWindow,
      doc: fakeDoc() as unknown as FocusDocument,
      post,
    });
    setFocusView(GCTK);
    await vi.advanceTimersByTimeAsync(FOCUS_SETTLE_MS);
    expect(post).toHaveBeenCalledTimes(1); // start still in flight
    release({ ok: true, status: 200 });
    await vi.advanceTimersByTimeAsync(0);
    expect(post).toHaveBeenCalledTimes(2);
    expect(JSON.parse(post.mock.calls[1][0] as unknown as string).symbol).toBe('GCTK');
  });

  it('sends nothing from the sample desk', async () => {
    vi.useFakeTimers();
    const r = start(fakeWin('?view=sample'));
    setFocusView(GCTK);
    await vi.advanceTimersByTimeAsync(FOCUS_HEARTBEAT_MS);
    expect(r.post).not.toHaveBeenCalled();
  });

  it('names a plain browser tab as browser', () => {
    const r = start(fakeWin('', false));
    expect(r.bodies()[0].role).toBe('browser');
    expect(EMPTY_FOCUS_VIEW.symbol).toBeNull();
  });
});
