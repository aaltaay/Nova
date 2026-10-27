/**
 * The browser development desk holds new code until the operator clicks Reload
 * (#612; architecture/schema/desk-ops.md, "The browser development desk holds
 * new code").
 *
 * A checkout change under a running `npm run dev` -- an agent's edit, a pull,
 * the installed desk's backend bringing the checkout to its release -- used to
 * hot-replace or reload every open trading page. With the hold on (the
 * default), the dev server sends no hot update and no full reload: it runs with
 * `server.hmr: false`, turns any update / full-reload Vite still sends into a
 * `nova:dev-code` notice, restarts itself on a config change as Vite would, and
 * stamps each page's own revision into its HTML. The page side
 * (`src/dev_reload_hold/`) shows the notice and holds `@vite/client`'s
 * reconnect reload. `NOVA_DEV_LIVE_RELOAD=1` restores Vite's normal behaviour.
 *
 * Only `vite` (serve) loads it; builds never do.
 */
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import type { HotPayload, Plugin, ViteDevServer } from 'vite';

export const LIVE_RELOAD_ENV = 'NOVA_DEV_LIVE_RELOAD';
/** Server to page: the code on disk (`CodeState`). */
export const CODE_EVENT = 'nova:dev-code';
/** Page to server, once it starts: answer me with `CODE_EVENT`. */
export const HELLO_EVENT = 'nova:dev-code:hello';
/** `<meta name=... content="<boot>.<seq>" data-head="<head>">`: the code this page was served. */
export const CODE_META = 'nova-dev-code';
/** Changes kept in `CodeState.recent`. */
export const RECENT_LIMIT = 20;
/** A burst of changes (a pull, a branch switch) is announced once it settles. */
export const ANNOUNCE_DEBOUNCE_MS = 200;
const RESTART_DEBOUNCE_MS = 150;
const GIT_TIMEOUT_MS = 2000;

export type CodeChangeKind = 'source' | 'html' | 'config' | 'reload';

export interface CodeChange {
  seq: number;
  kind: CodeChangeKind;
  /** Relative to the dev server's root (`frontend/`); null for a held Vite reload. */
  file: string | null;
}

export interface CodeState {
  schema_version: 1;
  boot: string;
  seq: number;
  head: string | null;
  at: string;
  /** Newest first. */
  recent: CodeChange[];
}

const TRUTHY = new Set(['1', 'true', 'yes', 'on']);

/** `NOVA_DEV_LIVE_RELOAD=1` (true / yes / on): Vite's normal hot updates and reloads. */
export function liveReloadRequested(value: string | undefined | null): boolean {
  return TRUTHY.has((value ?? '').trim().toLowerCase());
}

/** The checkout's short HEAD, or null when git cannot say. */
export function readGitHead(cwd: string): string | null {
  try {
    const out = execFileSync('git', ['rev-parse', '--short=9', 'HEAD'], {
      cwd,
      timeout: GIT_TIMEOUT_MS,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
    return /^[0-9a-f]{4,40}$/.test(out) ? out : null;
  } catch {
    return null;
  }
}

interface LedgerOptions {
  boot: string;
  readHead: () => string | null;
  now?: () => Date;
}

/** What the dev server has held since it started. */
export function createCodeLedger({ boot, readHead, now = () => new Date() }: LedgerOptions) {
  let seq = 0;
  // Read on first use: a build creates this plugin too and never serves a page.
  let head: string | null | undefined;
  let at = now().toISOString();
  let recent: CodeChange[] = [];
  return {
    record(kind: CodeChangeKind, file: string | null): void {
      seq += 1;
      at = now().toISOString();
      recent = [{ seq, kind, file }, ...recent].slice(0, RECENT_LIMIT);
    },
    /** Read HEAD again (once per announced burst, not per file). */
    refreshHead(): void {
      head = readHead();
    },
    state(): CodeState {
      if (head === undefined) head = readHead();
      return { schema_version: 1, boot, seq, head, at, recent: [...recent] };
    },
    revision(): string {
      return `${boot}.${seq}`;
    },
  };
}

export type CodeLedger = ReturnType<typeof createCodeLedger>;

export interface WatchEvent {
  /** Absolute, forward slashes (as Vite's watcher reports after normalizePath). */
  file: string;
  event: 'change' | 'add' | 'unlink';
  root: string;
  /** vite.config.ts, the files it imports, the .env files. */
  configFiles: readonly string[];
  /** The client module graph holds this file: some open page may run it. */
  inClientGraph: boolean;
}

const norm = (p: string) => p.replace(/\\/g, '/');

/** Which held change a watcher event is, or null when no page runs that file. */
export function classifyWatchEvent({ file, root, configFiles, inClientGraph }: WatchEvent): CodeChangeKind | null {
  const f = norm(file);
  if (configFiles.some((c) => norm(c) === f)) return 'config';
  const r = norm(root).replace(/\/$/, '');
  const inRoot = f.startsWith(`${r}/`) && !f.includes('/node_modules/');
  if (inRoot && f.endsWith('.html')) return 'html';
  if (inClientGraph) return 'source';
  return null;
}

/** A payload that would hot-replace or reload an open page. */
export function isHeldPayload(payload: HotPayload): boolean {
  return payload.type === 'update' || payload.type === 'full-reload' || payload.type === 'prune';
}

/** The .env files Vite reads for this mode (the same four names Vite watches). */
export function envFilesForMode(mode: string, envDir: string | false): string[] {
  if (envDir === false) return [];
  return ['.env', '.env.local', `.env.${mode}`, `.env.${mode}.local`].map((name) =>
    norm(path.resolve(envDir, name)),
  );
}

interface PluginOptions {
  /** True holds; false (NOVA_DEV_LIVE_RELOAD=1) leaves Vite alone. */
  hold: boolean;
  /** The checkout whose HEAD the notice names. */
  repoRoot: string;
}

function relativeTo(root: string, file: string): string {
  return norm(path.relative(root, file)) || file;
}

/** The dev-server half of the hold. */
export function novaReloadHoldPlugin({ hold, repoRoot }: PluginOptions): Plugin {
  const ledger = createCodeLedger({
    boot: Date.now().toString(36),
    readHead: () => readGitHead(repoRoot),
  });
  return {
    name: 'nova-reload-hold',
    apply: 'serve',
    config() {
      return hold ? { server: { hmr: false } } : undefined;
    },
    transformIndexHtml() {
      if (!hold) return undefined;
      const state = ledger.state();
      return [
        {
          tag: 'meta',
          attrs: { name: CODE_META, content: ledger.revision(), 'data-head': state.head ?? '' },
          injectTo: 'head',
        },
      ];
    },
    configureServer(server) {
      if (hold) installHold(server, ledger);
    },
  };
}

function installHold(server: ViteDevServer, ledger: CodeLedger): void {
  const { config, ws, watcher } = server;
  const root = config.root;
  const configFiles = [
    ...(config.configFile ? [norm(config.configFile)] : []),
    ...config.configFileDependencies.map(norm),
    ...envFilesForMode(config.mode, config.envDir),
  ];
  let announceTimer: ReturnType<typeof setTimeout> | null = null;
  let restartTimer: ReturnType<typeof setTimeout> | null = null;

  const announce = () => {
    if (announceTimer) clearTimeout(announceTimer);
    announceTimer = setTimeout(() => {
      announceTimer = null;
      ledger.refreshHead();
      send({ type: 'custom', event: CODE_EVENT, data: ledger.state() });
    }, ANNOUNCE_DEBOUNCE_MS);
  };

  // `server.ws` is the client environment's hot channel (Vite 8): every update
  // and full reload for a page goes through this one `send`.
  const send = ws.send.bind(ws) as (payload: HotPayload) => void;
  ws.send = ((...args: unknown[]) => {
    const payload = args[0];
    if (payload && typeof payload === 'object' && isHeldPayload(payload as HotPayload)) {
      ledger.record('reload', null);
      announce();
      return;
    }
    (send as (...a: unknown[]) => void)(...args);
  }) as typeof ws.send;

  ws.on(HELLO_EVENT, (_data: unknown, client: { send: (event: string, data: unknown) => void }) => {
    client.send(CODE_EVENT, ledger.state());
  });

  const restart = () => {
    if (restartTimer) clearTimeout(restartTimer);
    restartTimer = setTimeout(() => {
      restartTimer = null;
      config.logger.info('[nova] config changed: restarting the dev server; open pages wait for Reload (#612).', {
        timestamp: true,
      });
      server.restart().catch((err: unknown) => config.logger.error(String(err)));
    }, RESTART_DEBOUNCE_MS + ANNOUNCE_DEBOUNCE_MS);
  };

  const onEvent = (event: WatchEvent['event']) => (file: string) => {
    const abs = norm(path.resolve(file));
    const graph = server.environments.client.moduleGraph;
    const kind = classifyWatchEvent({
      file: abs,
      event,
      root,
      configFiles,
      inClientGraph: (graph.getModulesByFile(abs)?.size ?? 0) > 0,
    });
    if (!kind) return;
    ledger.record(kind, relativeTo(root, abs));
    announce();
    if (kind === 'config') restart();
  };
  watcher.on('change', onEvent('change'));
  watcher.on('add', onEvent('add'));
  watcher.on('unlink', onEvent('unlink'));
}
