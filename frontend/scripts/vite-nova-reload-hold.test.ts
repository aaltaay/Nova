import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import type { HotPayload, ViteDevServer } from 'vite';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ANNOUNCE_DEBOUNCE_MS,
  CODE_EVENT,
  CODE_META,
  createCodeLedger,
  envFilesForMode,
  HELLO_EVENT,
  isHeldPayload,
  classifyWatchEvent,
  liveReloadRequested,
  novaReloadHoldPlugin,
  RECENT_LIMIT,
  type CodeState,
} from './vite-nova-reload-hold';

const ROOT = '/repo/frontend';

describe('liveReloadRequested (NOVA_DEV_LIVE_RELOAD)', () => {
  it('turns the hold off only when asked', () => {
    for (const v of ['1', 'true', 'YES', ' on ']) expect(liveReloadRequested(v)).toBe(true);
    for (const v of [undefined, null, '', '0', 'false', 'off', 'later']) expect(liveReloadRequested(v)).toBe(false);
  });
});

describe('classifyWatchEvent', () => {
  const base = { root: ROOT, configFiles: [`${ROOT}/vite.config.ts`, '/repo/.env'], inClientGraph: false };

  it('a file an open page runs is a source change, whatever the event', () => {
    for (const event of ['change', 'add', 'unlink'] as const) {
      expect(classifyWatchEvent({ ...base, event, file: `${ROOT}/src/App.tsx`, inClientGraph: true })).toBe('source');
    }
  });

  it('a file no page runs is not a change any page has to hear about', () => {
    expect(classifyWatchEvent({ ...base, event: 'change', file: `${ROOT}/src/App.test.tsx` })).toBeNull();
    expect(classifyWatchEvent({ ...base, event: 'add', file: `${ROOT}/src/newThing.ts` })).toBeNull();
  });

  it('an HTML entry is held even before any module graph knows it', () => {
    expect(classifyWatchEvent({ ...base, event: 'change', file: `${ROOT}/index.html` })).toBe('html');
    expect(classifyWatchEvent({ ...base, event: 'change', file: `${ROOT}/node_modules/x/index.html` })).toBeNull();
  });

  it('the config, its imports and the .env files restart the server', () => {
    expect(classifyWatchEvent({ ...base, event: 'change', file: `${ROOT}/vite.config.ts` })).toBe('config');
    expect(classifyWatchEvent({ ...base, event: 'change', file: '/repo/.env', inClientGraph: true })).toBe('config');
  });

  it('reads Windows paths the same way', () => {
    expect(
      classifyWatchEvent({ ...base, root: 'C:\\Nova\\frontend', event: 'change', file: 'C:\\Nova\\frontend\\index.html' }),
    ).toBe('html');
  });
});

describe('isHeldPayload', () => {
  it('holds whatever would hot-replace or reload a page, passes the rest', () => {
    expect(isHeldPayload({ type: 'update', updates: [] })).toBe(true);
    expect(isHeldPayload({ type: 'full-reload', path: '*' })).toBe(true);
    expect(isHeldPayload({ type: 'prune', paths: [] })).toBe(true);
    expect(isHeldPayload({ type: 'custom', event: 'x' })).toBe(false);
    expect(isHeldPayload({ type: 'connected' })).toBe(false);
    expect(isHeldPayload({ type: 'error', err: { message: 'm', stack: '' } })).toBe(false);
  });
});

describe('envFilesForMode', () => {
  it('names the four files Vite reads', () => {
    expect(envFilesForMode('development', '/repo/frontend')).toEqual([
      '/repo/frontend/.env',
      '/repo/frontend/.env.local',
      '/repo/frontend/.env.development',
      '/repo/frontend/.env.development.local',
    ]);
    expect(envFilesForMode('development', false)).toEqual([]);
  });
});

describe('createCodeLedger', () => {
  it('counts held changes, newest first, and keeps the last few', () => {
    const readHead = vi.fn(() => 'abc1234');
    const ledger = createCodeLedger({ boot: 'b1', readHead, now: () => new Date('2026-10-27T14:00:00Z') });
    expect(readHead).not.toHaveBeenCalled(); // a build never reads git
    expect(ledger.revision()).toBe('b1.0');
    for (let i = 1; i <= RECENT_LIMIT + 5; i++) ledger.record('source', `src/f${i}.ts`);
    const state = ledger.state();
    expect(state).toMatchObject({ schema_version: 1, boot: 'b1', seq: RECENT_LIMIT + 5, head: 'abc1234' });
    expect(state.recent).toHaveLength(RECENT_LIMIT);
    expect(state.recent[0]).toEqual({ seq: RECENT_LIMIT + 5, kind: 'source', file: `src/f${RECENT_LIMIT + 5}.ts` });
    expect(ledger.revision()).toBe(`b1.${RECENT_LIMIT + 5}`);
  });

  it('reads HEAD again when told to (once per burst)', () => {
    let head = 'aaa1111';
    const ledger = createCodeLedger({ boot: 'b', readHead: () => head });
    expect(ledger.state().head).toBe('aaa1111');
    head = 'bbb2222';
    expect(ledger.state().head).toBe('aaa1111');
    ledger.refreshHead();
    expect(ledger.state().head).toBe('bbb2222');
  });
});

type Listener = (...args: unknown[]) => void;

function fakeServer(graphFiles: string[] = []) {
  const watchers: Record<string, Listener[]> = {};
  const wsListeners: Record<string, Listener[]> = {};
  const sent: HotPayload[] = [];
  const ws = {
    send: vi.fn((p: HotPayload) => sent.push(p)),
    on: vi.fn((event: string, fn: Listener) => (wsListeners[event] ??= []).push(fn)),
  };
  const server = {
    config: {
      root: ROOT,
      mode: 'development',
      envDir: ROOT,
      configFile: `${ROOT}/vite.config.ts`,
      configFileDependencies: [`${ROOT}/vite.config.ts`, `${ROOT}/scripts/vite-nova-reload-hold.ts`],
      logger: { info: vi.fn(), error: vi.fn() },
    },
    ws,
    watcher: { on: (event: string, fn: Listener) => (watchers[event] ??= []).push(fn) },
    environments: {
      client: {
        moduleGraph: {
          getModulesByFile: (f: string) => (graphFiles.includes(f) ? new Set([{}]) : undefined),
        },
      },
    },
    restart: vi.fn(async () => {}),
  };
  const fire = (event: string, file: string) => watchers[event]?.forEach((fn) => fn(file));
  return { server, ws, sent, wsListeners, fire };
}

function startPlugin(hold: boolean, graphFiles: string[] = []) {
  const plugin = novaReloadHoldPlugin({ hold, repoRoot: '/nonexistent-repo' });
  const fake = fakeServer(graphFiles);
  (plugin.configureServer as (s: ViteDevServer) => void)(fake.server as unknown as ViteDevServer);
  return { plugin, ...fake };
}

const notices = (sent: HotPayload[]) =>
  sent.filter((p): p is Extract<HotPayload, { type: 'custom' }> => p.type === 'custom' && p.event === CODE_EVENT);

describe('novaReloadHoldPlugin', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('runs only on the dev server, and turns Vite HMR off only while it holds', () => {
    expect(novaReloadHoldPlugin({ hold: true, repoRoot: ROOT }).apply).toBe('serve');
    const config = (hold: boolean) =>
      (novaReloadHoldPlugin({ hold, repoRoot: ROOT }).config as () => unknown)();
    expect(config(true)).toEqual({ server: { hmr: false } });
    expect(config(false)).toBeUndefined();
  });

  it("stamps each page with the revision it was served, and nothing under NOVA_DEV_LIVE_RELOAD", () => {
    const tags = (hold: boolean) =>
      (novaReloadHoldPlugin({ hold, repoRoot: '/nonexistent-repo' }).transformIndexHtml as () => unknown)();
    const [meta] = tags(true) as { tag: string; attrs: Record<string, string> }[];
    expect(meta.tag).toBe('meta');
    expect(meta.attrs.name).toBe(CODE_META);
    expect(meta.attrs.content).toMatch(/^[0-9a-z]+\.0$/);
    expect(tags(false)).toBeUndefined();
  });

  it('under NOVA_DEV_LIVE_RELOAD leaves the server exactly as Vite made it', () => {
    const { ws, sent } = startPlugin(false);
    const original = ws.send;
    expect(ws.send).toBe(original);
    ws.send({ type: 'full-reload', path: '*' });
    expect(sent).toEqual([{ type: 'full-reload', path: '*' }]);
    expect(ws.on).not.toHaveBeenCalled();
  });

  it('turns a full reload or an update into one notice, and passes everything else', () => {
    const { ws, sent } = startPlugin(true);
    ws.send({ type: 'full-reload', path: '*' });
    ws.send({ type: 'update', updates: [] });
    ws.send({ type: 'custom', event: 'other', data: 1 });
    expect(sent).toEqual([{ type: 'custom', event: 'other', data: 1 }]);
    vi.advanceTimersByTime(ANNOUNCE_DEBOUNCE_MS);
    const [notice] = notices(sent);
    const state = notice.data as CodeState;
    expect(state.seq).toBe(2);
    expect(state.recent.map((c) => c.kind)).toEqual(['reload', 'reload']);
    expect(sent.some((p) => p.type === 'full-reload' || p.type === 'update')).toBe(false);
  });

  it('announces a burst of source changes once it settles, to every page', () => {
    const files = [`${ROOT}/src/App.tsx`, `${ROOT}/src/chart/x.ts`];
    const { fire, sent } = startPlugin(true, files);
    fire('change', files[0]);
    fire('unlink', files[1]);
    fire('change', `${ROOT}/README.md`);
    expect(notices(sent)).toHaveLength(0);
    vi.advanceTimersByTime(ANNOUNCE_DEBOUNCE_MS);
    const all = notices(sent);
    expect(all).toHaveLength(1);
    const state = all[0].data as CodeState;
    expect(state.seq).toBe(2);
    expect(state.recent).toEqual([
      { seq: 2, kind: 'source', file: 'src/chart/x.ts' },
      { seq: 1, kind: 'source', file: 'src/App.tsx' },
    ]);
    expect(state.head).toBeNull(); // no git at /nonexistent-repo
  });

  it('answers a page that just started with the code on disk, to that page alone', () => {
    const { fire, wsListeners } = startPlugin(true, [`${ROOT}/src/App.tsx`]);
    fire('change', `${ROOT}/src/App.tsx`);
    const client = { send: vi.fn() };
    wsListeners[HELLO_EVENT][0]({ boot: 'x', seq: 0 }, client);
    expect(client.send).toHaveBeenCalledWith(CODE_EVENT, expect.objectContaining({ seq: 1 }));
  });

  it('restarts the server on a config change, as Vite would, after telling the pages', () => {
    const { fire, server, sent } = startPlugin(true);
    fire('change', `${ROOT}/scripts/vite-nova-reload-hold.ts`);
    vi.advanceTimersByTime(ANNOUNCE_DEBOUNCE_MS);
    expect(notices(sent)[0].data).toMatchObject({ recent: [{ kind: 'config' }] });
    expect(server.restart).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1000);
    expect(server.restart).toHaveBeenCalledTimes(1);
  });
});

/**
 * The page holds `@vite/client`'s reconnect reload only because the client
 * awaits our listeners first (src/dev_reload_hold/installReloadHold.ts). This
 * reads the installed client so a Vite upgrade that changes the order fails
 * here instead of reloading the operator's desk.
 */
describe('the installed @vite/client still awaits our listeners first', () => {
  const require = createRequire(import.meta.url);
  const clientPath = path.join(path.dirname(require.resolve('vite/package.json')), 'dist/client/client.mjs');
  const client = fs.readFileSync(clientPath, 'utf8');
  const order = (...needles: string[]) => {
    let at = -1;
    for (const needle of needles) {
      const next = client.indexOf(needle, at + 1);
      expect(next, `${needle} after offset ${at}`).toBeGreaterThan(at);
      at = next;
    }
  };

  it('listeners are awaited, all of them', () => {
    expect(client).toMatch(/async notifyListeners\(event, data\) \{\s*const cbs = [^;]+;\s*if \(cbs\) await Promise\.allSettled/);
  });

  it('before an update, a full reload, and the reconnect poll-then-reload', () => {
    order('case "update":', 'await activeHmrClient.notifyListeners("vite:beforeUpdate"', 'queueUpdate');
    order('case "custom":', 'await activeHmrClient.notifyListeners(payload.event, payload.data);', 'vite:ws:disconnect', 'await waitForSuccessfulPing', 'location.reload()');
    order('case "full-reload":', 'await activeHmrClient.notifyListeners("vite:beforeFullReload"', 'pageReload()');
  });
});
