/**
 * The page half of the browser reload hold (#612): listens on the dev server's
 * hot channel and keeps `@vite/client` from hot-replacing or reloading this
 * page. See architecture/schema/desk-ops.md, "The browser development desk
 * holds new code".
 *
 * `@vite/client` (Vite 8.3.4) awaits every listener of `vite:beforeUpdate`,
 * `vite:beforeFullReload` and `vite:ws:disconnect` before it applies an update,
 * reloads, or polls a restarted server and reloads. Our listeners return a
 * promise that never settles, so none of those ever happens; the notice's
 * Reload is the only way the page reloads. `viteClientOrder.test.ts` fails if
 * a Vite upgrade changes that order.
 */
import {
  CODE_EVENT,
  HELLO_EVENT,
  initialView,
  readRunningCode,
  runningFromHtml,
  withDisconnect,
  withFolded,
  withHeldUpdate,
  withServerBack,
  withServerCode,
  type HoldView,
  type RunningCode,
} from './holdModel';

/** The part of `import.meta.hot` the hold uses. */
export interface HotChannel {
  on(event: string, cb: (data: unknown) => unknown): void;
  send(event: string, data?: unknown): void;
}

/** Ask the stopped dev server again this often. */
export const SERVER_POLL_MS = 2000;
/**
 * Once it is back, look again this often: the page's socket is gone for good
 * (@vite/client never reconnects it), so this is how the notice keeps saying
 * whether the server is up and which HEAD it serves.
 */
export const SERVER_RECHECK_MS = 10_000;

export interface HoldStore {
  get(): HoldView;
  subscribe(listener: () => void): () => void;
  fold(folded: boolean): void;
}

interface Store extends HoldStore {
  update(fn: (view: HoldView) => HoldView): void;
}

export function createHoldStore(initial: HoldView): Store {
  let view = initial;
  const listeners = new Set<() => void>();
  const update = (fn: (view: HoldView) => HoldView) => {
    const next = fn(view);
    if (next === view) return;
    view = next;
    listeners.forEach((l) => l());
  };
  return {
    get: () => view,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    update,
    fold: (folded) => update((v) => withFolded(v, folded)),
  };
}

export interface InstallDeps {
  doc: Pick<Document, 'querySelector'>;
  hot: HotChannel | undefined;
  /** The dev server's HTML now; rejects while it is down. */
  fetchPage: () => Promise<string>;
  setTimer?: (fn: () => void, ms: number) => unknown;
}

/** A promise that never settles: what holds `@vite/client`. */
const holdForever = () => new Promise<void>(() => {});

/** Null when this page has no hold (a build, or NOVA_DEV_LIVE_RELOAD=1 on the dev server). */
export function installReloadHold({ doc, hot, fetchPage, setTimer = setTimeout }: InstallDeps): HoldStore | null {
  const running: RunningCode | null = readRunningCode(doc);
  if (!running || !hot) return null;
  const store = createHoldStore(initialView(running));

  hot.on(CODE_EVENT, (data) => store.update((v) => withServerCode(v, data)));
  hot.on('vite:beforeUpdate', () => {
    store.update(withHeldUpdate);
    return holdForever();
  });
  hot.on('vite:beforeFullReload', () => {
    store.update(withHeldUpdate);
    return holdForever();
  });

  let polling = false;
  const poll = () => {
    fetchPage().then(
      (html) => {
        store.update((v) => withServerBack(v, runningFromHtml(html)));
        setTimer(poll, SERVER_RECHECK_MS);
      },
      () => {
        store.update(withDisconnect);
        setTimer(poll, SERVER_POLL_MS);
      },
    );
  };
  hot.on('vite:ws:disconnect', () => {
    store.update(withDisconnect);
    if (!polling) {
      polling = true;
      setTimer(poll, SERVER_POLL_MS);
    }
    return holdForever();
  });

  // The HTML was served a moment ago; a change since then still reaches this page.
  hot.send(HELLO_EVENT, { boot: running.boot, seq: running.seq });
  return store;
}
