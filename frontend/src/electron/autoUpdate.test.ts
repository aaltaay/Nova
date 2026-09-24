/**
 * The desk must never download or install an update by itself (#347; operator
 * ask 2026-09-23). These cover the glue around updatePolicy.mjs: what
 * electron-updater is configured to do, the question a found release raises
 * (the desk's notice when the window listens, else a dialog), what happens on
 * Update, Later and Restart, and when the local engine will not stop.
 * The installer is fetched by releaseDownload.mjs in resumable chunks and
 * handed back to electron-updater; its own download is the fallback.
 * The open desk re-checks every two hours, never in weekday trading hours.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  UPDATE_FIRST_CHECK_DELAY_MS,
  UPDATE_RECHECK_INTERVAL_MS,
  UPDATE_RECHECK_TICK_MS,
} from '../../electron/updatePolicy.mjs';

type FakeUpdater = {
  autoDownload: boolean;
  autoInstallOnAppQuit: boolean;
  checkForUpdates: ReturnType<typeof vi.fn>;
  downloadUpdate: ReturnType<typeof vi.fn>;
};
type MenuRow = { label?: string; role?: string; submenu?: { label: string; click?: () => void }[] };
type DownloadOpts = { cacheDir: string; target: { url: string }; onProgress: (p: number) => void };
type Box = { buttons?: string[]; message?: string; detail?: string };
type IpcHandler = (event: { sender: unknown }, request?: unknown) => unknown;
type View = { notice: null | { stage: string; tag: string; notes: null | { releases: { tag: string }[] } } };

const h = vi.hoisted(() => ({
  boxes: [] as Box[],
  responses: [] as number[],
  installs: [] as unknown[][],
  updater: null as FakeUpdater | null,
  menu: [] as MenuRow[],
  // When true the fake updater exposes what a resumable download needs.
  resumable: false,
  // One double per download attempt, in order; the last one repeats.
  downloads: [] as ((opts: DownloadOpts) => Promise<string>)[],
  // One answer per check, in order: false = up to date. Empty: an update is available.
  available: [] as boolean[],
  // How long each check takes to answer, in order (ms); empty: at once.
  checkDelays: [] as number[],
  ipc: {} as Record<string, IpcHandler>,
  releases: [] as unknown[],
  opened: [] as string[],
}));

vi.mock('electron', () => ({
  app: { isPackaged: true, getVersion: () => '0.1.831', getPath: () => '' },
  dialog: {
    showMessageBox: vi.fn(async (...args: unknown[]) => {
      h.boxes.push(args[args.length - 1] as Box);
      return { response: h.responses.shift() ?? 1 };
    }),
  },
  Menu: {
    buildFromTemplate: (t: unknown) => t,
    setApplicationMenu: (m: MenuRow[]) => {
      h.menu = m;
    },
  },
  net: { fetch: vi.fn(async () => ({ ok: true, status: 200, json: async () => h.releases })) },
  ipcMain: {
    handle: (channel: string, handler: IpcHandler) => {
      h.ipc[channel] = handler;
    },
  },
  shell: {
    openExternal: vi.fn(async (url: string) => {
      h.opened.push(url);
    }),
  },
}));

vi.mock('../../electron/updateDownload.mjs', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../electron/updateDownload.mjs')>();
  return {
    ...real,
    downloadInstaller: vi.fn(async (opts: DownloadOpts) => {
      const next = h.downloads.length > 1 ? h.downloads.shift() : h.downloads[0];
      if (!next) throw new Error('downloadInstaller called without a test double');
      return next(opts);
    }),
  };
});

vi.mock('electron-updater', async () => {
  const { EventEmitter } = await import('node:events');
  class NsisUpdater extends EventEmitter {
    logger: unknown;
    autoDownload = true;
    autoInstallOnAppQuit = true;
    updateInfoAndProvider: unknown = null;
    checkForUpdates = vi.fn(async () => {
      const updateInfo = { version: '0.1.832' };
      this.emit('checking-for-update');
      const delay = h.checkDelays.shift() ?? 0;
      if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
      if (!(h.available.shift() ?? true)) {
        this.emit('update-not-available', { version: '0.1.831' });
        return { isUpdateAvailable: false, updateInfo: { version: '0.1.831' } };
      }
      if (h.resumable) {
        this.updateInfoAndProvider = {
          provider: {
            resolveFiles: () => [
              {
                url: new URL('https://github.com/aaltaay/Nova/releases/download/v832/Nova-Setup-v832.exe'),
                info: { sha512: 'abc', size: 100 },
              },
            ],
          },
        };
      }
      this.emit('update-available', updateInfo);
      return { isUpdateAvailable: true, updateInfo };
    });
    getOrCreateDownloadHelper = vi.fn(async () => ({ cacheDir: 'C:/cache/nova-updater' }));
    // electron-updater's own download, or its hand-off of a file already in the cache.
    downloadUpdate = vi.fn(async () => {
      this.emit('download-progress', { percent: 50 });
      this.emit('update-downloaded', { version: '0.1.832' });
      return [];
    });
    quitAndInstall = vi.fn((...args: unknown[]) => h.installs.push(args));
    constructor() {
      super();
      h.updater = this;
    }
  }
  return { NsisUpdater };
});

const realPlatform = process.platform;
const contents = { send: vi.fn(), on: vi.fn(), isDestroyed: () => false };
const win = {
  isDestroyed: () => false,
  isFocused: () => true,
  once: vi.fn(),
  setProgressBar: vi.fn(),
  flashFrame: vi.fn(),
  webContents: contents,
};
const UPDATE = 0;
const RESTART = 0;
const LATER = 1;

async function start(deps: Record<string, unknown> = {}) {
  const { startAutoUpdate } = await import('../../electron/autoUpdate.mjs');
  const stopEngine = vi.fn(async () => true);
  const restartEngine = vi.fn(async () => {});
  await startAutoUpdate({
    getWindow: () => win,
    envPath: () => '',
    stopEngine,
    restartEngine,
    ...deps,
  });
  return { stopEngine, restartEngine };
}

async function startAndCheck(deps: Record<string, unknown> = {}) {
  const engine = await start(deps);
  // Nothing happens until the delayed startup check fires.
  expect(h.updater?.checkForUpdates).not.toHaveBeenCalled();
  // Not runAllTimers: the re-check clock repeats for as long as the desk runs.
  await vi.advanceTimersByTimeAsync(UPDATE_FIRST_CHECK_DELAY_MS);
  return engine;
}

function helpLabels() {
  return (h.menu.find((row) => row.role === 'help')?.submenu ?? []).map((row) => row.label);
}

/** The desk's page subscribes, as desktop_update/useDesktopUpdate.ts does on mount. */
function subscribe(sender: unknown = contents) {
  return h.ipc['nova:update:subscribe']({ sender });
}

async function answer(action: string, extra: Record<string, unknown> = {}, sender: unknown = contents) {
  const reply = h.ipc['nova:update:act']({ sender }, { action, ...extra });
  await vi.advanceTimersByTimeAsync(0);
  return reply;
}

function lastView(): View {
  return contents.send.mock.calls.at(-1)?.[1] as View;
}

const releaseRow = (tag: string, summary: string) => ({
  tag_name: tag,
  html_url: `https://github.com/aaltaay/Nova/releases/tag/${tag}`,
  published_at: '2026-09-23T20:00:00Z',
  body: `## What's new\n\n<!-- nova-release-notes ${JSON.stringify({
    schema_version: 1,
    tag,
    title: `Title of ${tag}`,
    kind: 'feat',
    scope: 'desk',
    pr: 540,
    summary,
    points: [],
  })} -->`,
});

beforeEach(() => {
  vi.resetModules();
  vi.useFakeTimers();
  h.boxes.length = 0;
  h.responses.length = 0;
  h.installs.length = 0;
  h.menu = [];
  h.resumable = false;
  h.downloads = [];
  h.available.length = 0;
  h.checkDelays.length = 0;
  h.ipc = {};
  h.releases = [];
  h.opened.length = 0;
  win.setProgressBar.mockClear();
  contents.send.mockClear();
  Object.defineProperty(process, 'platform', { value: 'win32', configurable: true });
});

afterEach(() => {
  vi.useRealTimers();
  Object.defineProperty(process, 'platform', { value: realPlatform, configurable: true });
  delete process.env.NOVA_UPDATE_CHECK;
});

describe('startAutoUpdate', () => {
  it('asks before downloading, and installs only when the operator picks Restart', async () => {
    h.releases = [releaseRow('v832', 'Release notes show after an update.')];
    h.responses.push(UPDATE, RESTART);
    const { stopEngine } = await startAndCheck();
    expect(h.updater?.autoDownload).toBe(false);
    expect(h.updater?.autoInstallOnAppQuit).toBe(false);
    expect(h.boxes[0]?.buttons).toEqual(['Update', 'Later']);
    expect(h.boxes[0]?.message).toBe('Nova v832 is available (you have v831).');
    expect(h.boxes[0]?.detail).toContain('Release notes show after an update.');
    expect(win.setProgressBar).toHaveBeenCalledWith(0.5);
    expect(h.boxes[1]?.buttons).toEqual(['Restart to update', 'Later']);
    expect(stopEngine).toHaveBeenCalled();
    // Silent install into the existing location, then relaunch the new version.
    expect(h.installs).toEqual([[true, true]]);
  });

  it('downloads nothing when the operator picks Later', async () => {
    h.responses.push(LATER);
    const { stopEngine } = await startAndCheck();
    expect(h.updater?.downloadUpdate).not.toHaveBeenCalled();
    expect(stopEngine).not.toHaveBeenCalled();
    expect(helpLabels()[0]).toBe('Update to v832…');
  });

  it('installs nothing when the operator picks Later at the restart', async () => {
    h.responses.push(UPDATE, LATER);
    const { stopEngine } = await startAndCheck();
    expect(h.updater?.downloadUpdate).toHaveBeenCalled();
    expect(stopEngine).not.toHaveBeenCalled();
    expect(h.installs).toEqual([]);
    expect(helpLabels()[0]).toBe('Restart to Update (v832)');
  });

  it('refuses to install while the local engine is still running, and revives it', async () => {
    h.responses.push(UPDATE, RESTART);
    const { restartEngine } = await startAndCheck({ stopEngine: vi.fn(async () => false) });
    expect(h.installs).toEqual([]);
    expect(restartEngine).toHaveBeenCalled();
    expect(h.boxes.at(-1)?.message).toContain('did not install');
  });

  it('never checks on its own when the setting is off', async () => {
    process.env.NOVA_UPDATE_CHECK = '0';
    await start();
    await vi.runAllTimersAsync();
    expect(h.updater?.checkForUpdates).not.toHaveBeenCalled();
  });

  it('stays out of a dev checkout entirely', async () => {
    h.updater = null;
    const electron = await import('electron');
    (electron.app as { isPackaged: boolean }).isPackaged = false;
    await start();
    await vi.runAllTimersAsync();
    expect(h.updater).toBeNull();
    // The page still gets an answer: nothing to show.
    expect(subscribe()).toMatchObject({ schema_version: 1, notice: null, whats_new: null });
    (electron.app as { isPackaged: boolean }).isPackaged = true;
  });
});

describe('the notice on the desk', () => {
  it('tells the page instead of opening a dialog, and acts on its answers', async () => {
    h.releases = [releaseRow('v832', 'Notes for v832.')];
    await start();
    subscribe();
    await vi.advanceTimersByTimeAsync(UPDATE_FIRST_CHECK_DELAY_MS);
    expect(h.boxes).toEqual([]);
    expect(lastView().notice).toMatchObject({ stage: 'available', tag: 'v832' });
    expect(lastView().notice?.notes?.releases.map((r) => r.tag)).toEqual(['v832']);
    expect(h.updater?.downloadUpdate).not.toHaveBeenCalled();

    expect(await answer('download')).toEqual({ ok: true });
    expect(h.updater?.downloadUpdate).toHaveBeenCalled();
    expect(lastView().notice?.stage).toBe('ready');
    expect(h.boxes).toEqual([]); // the notice asks for the restart too
    expect(h.installs).toEqual([]);

    await answer('restart');
    expect(h.installs).toEqual([[true, true]]);
  });

  it('hides the notice for this version on Later, and the Help menu raises it again', async () => {
    await start();
    subscribe();
    await vi.advanceTimersByTimeAsync(UPDATE_FIRST_CHECK_DELAY_MS);
    await answer('later');
    expect(lastView().notice).toBeNull();
    const update = h.menu.find((row) => row.role === 'help')?.submenu?.[0];
    expect(update?.label).toBe('Update to v832…');
    update?.click?.();
    await vi.advanceTimersByTimeAsync(0);
    expect(lastView().notice?.stage).toBe('ready'); // Update from the menu downloads, and the notice follows it
  });

  it('answers only the main window, and opens only Nova release links', async () => {
    await start();
    const popout = { send: vi.fn(), on: vi.fn(), isDestroyed: () => false };
    expect(subscribe(popout)).toBeNull();
    expect(await answer('download', {}, popout)).toMatchObject({ ok: false });
    await answer('open-link', { url: 'https://example.com/phish' });
    await answer('open-link', { url: 'https://github.com/aaltaay/Nova/pull/540' });
    expect(h.opened).toEqual(['https://github.com/aaltaay/Nova/pull/540']);
  });
});

describe('re-checks while the desk stays open', () => {
  const MINUTE = 60_000;

  it('asks GitHub again every two hours outside trading hours, quietly', async () => {
    vi.setSystemTime(new Date('2026-09-26T14:00:00Z')); // Saturday 10:00 ET
    h.available.push(false, false);
    await startAndCheck();
    expect(h.updater?.checkForUpdates).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(UPDATE_RECHECK_INTERVAL_MS - UPDATE_RECHECK_TICK_MS);
    expect(h.updater?.checkForUpdates).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(2 * UPDATE_RECHECK_TICK_MS);
    expect(h.updater?.checkForUpdates).toHaveBeenCalledTimes(2);
    expect(h.boxes).toEqual([]); // "up to date" is never announced by an automatic check
  });

  it('holds re-checks through weekday trading hours, then catches up after the close', async () => {
    vi.setSystemTime(new Date('2026-09-23T13:00:00Z')); // Wednesday 09:00 ET
    h.available.push(false, false);
    await startAndCheck(); // the launch check itself is never held
    expect(h.updater?.checkForUpdates).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(6 * 60 * MINUTE + 50 * MINUTE); // 15:50 ET
    expect(h.updater?.checkForUpdates).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(20 * MINUTE); // 16:10 ET
    expect(h.updater?.checkForUpdates).toHaveBeenCalledTimes(2);
  });

  it("holds a re-check's find through trading hours and asks after the close", async () => {
    vi.setSystemTime(new Date('2026-09-23T08:30:00Z')); // Wednesday 04:30 ET
    h.available.push(false); // the launch check finds nothing; the 06:40 re-check finds v832...
    h.checkDelays.push(0, 30 * MINUTE); // ...and answers at 07:10 ET, inside trading hours
    await startAndCheck();
    await vi.advanceTimersByTimeAsync(3 * 60 * MINUTE); // 07:30 ET
    expect(h.updater?.checkForUpdates).toHaveBeenCalledTimes(2);
    expect(helpLabels()[0]).toBe('Update to v832…');
    expect(h.boxes).toEqual([]);
    await vi.advanceTimersByTimeAsync(8 * 60 * MINUTE + 20 * MINUTE); // 15:50 ET
    expect(h.boxes).toEqual([]);
    h.responses.push(LATER);
    await vi.advanceTimersByTimeAsync(20 * MINUTE); // 16:10 ET
    expect(h.boxes).toHaveLength(1);
    expect(h.boxes[0]?.buttons).toEqual(['Update', 'Later']);
    expect(h.updater?.downloadUpdate).not.toHaveBeenCalled();
    // Later is not re-asked this session.
    await vi.advanceTimersByTimeAsync(4 * 60 * MINUTE);
    expect(h.boxes).toHaveLength(1);
  });
});

describe('resumable installer download', () => {
  it("fetches the installer itself into electron-updater's cache, then lets electron-updater verify it", async () => {
    h.resumable = true;
    const seen: DownloadOpts[] = [];
    h.downloads = [
      async (opts) => {
        seen.push(opts);
        opts.onProgress(40);
        // electron-updater has not been asked to download anything yet.
        expect(h.updater?.downloadUpdate).not.toHaveBeenCalled();
        return `${opts.cacheDir}/pending/Nova-Setup-v832.exe`;
      },
    ];
    h.responses.push(UPDATE, LATER);
    await startAndCheck();
    expect(seen).toHaveLength(1);
    expect(seen[0].cacheDir).toBe('C:/cache/nova-updater');
    expect(seen[0].target.url).toBe('https://github.com/aaltaay/Nova/releases/download/v832/Nova-Setup-v832.exe');
    expect(win.setProgressBar).toHaveBeenCalledWith(0.4);
    expect(h.updater?.downloadUpdate).toHaveBeenCalledTimes(1);
    expect(h.boxes.at(-1)?.buttons).toEqual(['Restart to update', 'Later']);
  });

  it('says the download stopped, keeps its percent, and offers Resume instead of a failed check', async () => {
    h.resumable = true;
    h.downloads = [
      async (opts) => {
        opts.onProgress(45);
        throw new Error('net::ERR_SSL_PROTOCOL_ERROR (gave up on bytes 0-9; 0 kept)');
      },
    ];
    h.responses.push(UPDATE);
    await startAndCheck();
    expect(h.updater?.downloadUpdate).not.toHaveBeenCalled();
    expect(h.boxes).toHaveLength(1); // the question; an automatic check's failure is quiet
    expect(helpLabels()[0]).toBe('Download of v832 stopped at 45% — Resume');
    expect(helpLabels()[1]).toContain('ERR_SSL_PROTOCOL_ERROR');
  });

  it('resumes a stopped download at the next check without asking again', async () => {
    vi.setSystemTime(new Date('2026-09-26T14:00:00Z')); // Saturday 10:00 ET
    h.resumable = true;
    h.downloads = [
      async (opts) => {
        opts.onProgress(45);
        throw new Error('net::ERR_CONNECTION_RESET');
      },
      async (opts) => `${opts.cacheDir}/pending/Nova-Setup-v832.exe`,
    ];
    h.responses.push(UPDATE, LATER);
    await startAndCheck();
    expect(helpLabels()[0]).toBe('Download of v832 stopped at 45% — Resume');
    await vi.advanceTimersByTimeAsync(UPDATE_RECHECK_INTERVAL_MS + UPDATE_RECHECK_TICK_MS);
    expect(h.updater?.checkForUpdates).toHaveBeenCalledTimes(2);
    expect(h.boxes.map((b) => b.buttons?.[0])).toEqual(['Update', 'Restart to update']);
    expect(helpLabels()[0]).toBe('Restart to Update (v832)');
  });

  it("falls back to electron-updater's own download when it cannot plan a resumable one", async () => {
    h.resumable = false; // no provider to resolve the installer URL
    h.responses.push(UPDATE, LATER);
    await startAndCheck();
    expect(h.updater?.downloadUpdate).toHaveBeenCalledTimes(1);
    expect(h.boxes.at(-1)?.buttons).toEqual(['Restart to update', 'Later']);
  });
});
