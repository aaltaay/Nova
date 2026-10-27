/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CODE_EVENT, HELLO_EVENT, pendingSummary } from './holdModel';
import { installReloadHold, SERVER_POLL_MS, SERVER_RECHECK_MS, type HotChannel } from './installReloadHold';

function fakeHot() {
  const listeners = new Map<string, ((data: unknown) => unknown)[]>();
  const sent: [string, unknown][] = [];
  const hot: HotChannel = {
    on: (event, cb) => listeners.set(event, [...(listeners.get(event) ?? []), cb]),
    send: (event, data) => sent.push([event, data]),
  };
  /** What @vite/client does: call every listener and await them all. */
  const emit = (event: string, data?: unknown) =>
    Promise.allSettled((listeners.get(event) ?? []).map((cb) => cb(data)));
  return { hot, sent, emit, listeners };
}

function pageWithMeta(content: string | null) {
  document.head.innerHTML = content === null ? '' : `<meta name="nova-dev-code" content="${content}" data-head="aaa1111">`;
  return document;
}

/** Settles within a tick, or reports that it is still held. */
async function settles(p: Promise<unknown>): Promise<boolean> {
  let done = false;
  void p.then(() => (done = true));
  await vi.advanceTimersByTimeAsync(0);
  return done;
}

describe('installReloadHold', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    document.head.innerHTML = '';
  });

  it('does nothing on a page the dev server does not hold (NOVA_DEV_LIVE_RELOAD=1, or a build)', () => {
    const { hot, listeners, sent } = fakeHot();
    expect(installReloadHold({ doc: pageWithMeta(null), hot, fetchPage: vi.fn() })).toBeNull();
    expect(installReloadHold({ doc: pageWithMeta('b1.0'), hot: undefined, fetchPage: vi.fn() })).toBeNull();
    expect(listeners.size).toBe(0);
    expect(sent).toEqual([]);
  });

  it('says hello with its own revision, so a change made while it loaded still reaches it', () => {
    const { hot, sent } = fakeHot();
    installReloadHold({ doc: pageWithMeta('b1.4'), hot, fetchPage: vi.fn() });
    expect(sent).toEqual([[HELLO_EVENT, { boot: 'b1', seq: 4 }]]);
  });

  it('a server announcement makes the page pending; nothing else happens', async () => {
    const { hot, emit } = fakeHot();
    const store = installReloadHold({ doc: pageWithMeta('b1.0'), hot, fetchPage: vi.fn() })!;
    await emit(CODE_EVENT, { schema_version: 1, boot: 'b1', seq: 1, head: 'aaa1111', at: '', recent: [{ seq: 1, kind: 'source', file: 'src/App.tsx' }] });
    expect(pendingSummary(store.get())).toMatchObject({ changes: 1, files: ['src/App.tsx'] });
  });

  it("holds @vite/client's update and full reload forever, and shows why", async () => {
    const { hot, emit } = fakeHot();
    const store = installReloadHold({ doc: pageWithMeta('b1.0'), hot, fetchPage: vi.fn() })!;
    expect(await settles(emit('vite:beforeFullReload', { type: 'full-reload' }))).toBe(false);
    expect(await settles(emit('vite:beforeUpdate', { type: 'update', updates: [] }))).toBe(false);
    expect(store.get().heldUpdate).toBe(true);
    await vi.advanceTimersByTimeAsync(60 * 60 * 1000);
    expect(store.get().heldUpdate).toBe(true);
  });

  it('holds the reconnect reload, asks the server again every 2 s, and says when it is back', async () => {
    const { hot, emit } = fakeHot();
    const fetchPage = vi
      .fn<() => Promise<string>>()
      .mockRejectedValueOnce(new Error('down'))
      .mockRejectedValueOnce(new Error('down'))
      .mockResolvedValue('<meta name="nova-dev-code" content="b2.0" data-head="bbb2222">');
    const store = installReloadHold({ doc: pageWithMeta('b1.0'), hot, fetchPage })!;
    const held = emit('vite:ws:disconnect', {});
    expect(await settles(held)).toBe(false);
    expect(store.get().server).toBe('down');
    expect(fetchPage).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(SERVER_POLL_MS);
    await vi.advanceTimersByTimeAsync(SERVER_POLL_MS);
    expect(store.get().server).toBe('down');
    await vi.advanceTimersByTimeAsync(SERVER_POLL_MS);
    expect(fetchPage).toHaveBeenCalledTimes(3);
    expect(pendingSummary(store.get())).toMatchObject({ server: 'back', restarted: true, diskHead: 'bbb2222' });
    // Back is not a reload: the listener @vite/client awaits still holds.
    expect(await settles(held)).toBe(false);
    // The socket is gone for good, so the page keeps looking, more slowly, and follows a second stop.
    await vi.advanceTimersByTimeAsync(SERVER_RECHECK_MS - 1);
    expect(fetchPage).toHaveBeenCalledTimes(3);
    fetchPage.mockRejectedValueOnce(new Error('down again'));
    await vi.advanceTimersByTimeAsync(1);
    expect(store.get().server).toBe('down');
    fetchPage.mockResolvedValue('<meta name="nova-dev-code" content="b3.0" data-head="ddd4444">');
    await vi.advanceTimersByTimeAsync(SERVER_POLL_MS);
    expect(pendingSummary(store.get())).toMatchObject({ server: 'back', diskHead: 'ddd4444' });
  });

  it('Later folds the notice and unfolds it; the code stays pending either way', async () => {
    const { hot, emit } = fakeHot();
    const store = installReloadHold({ doc: pageWithMeta('b1.0'), hot, fetchPage: vi.fn() })!;
    const seen = vi.fn();
    store.subscribe(seen);
    await emit(CODE_EVENT, { schema_version: 1, boot: 'b1', seq: 1, head: null, at: '', recent: [] });
    store.fold(true);
    expect(store.get().folded).toBe(true);
    expect(pendingSummary(store.get())).not.toBeNull();
    store.fold(false);
    expect(seen).toHaveBeenCalledTimes(3);
  });
});
