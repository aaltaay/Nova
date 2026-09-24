/**
 * The "Updating Nova" window (updateSplash.mjs / updateSplash.ps1). On
 * 2026-09-23 "Restart to update" installed v976 correctly, but nothing of Nova
 * was on screen for 46 s and it read as "nothing happened". These pin how the
 * window is started -- the two obvious ways both fail on Windows (a detached
 * powershell.exe quits with no console; an attached one dies with Nova) -- and
 * that the script and the module agree.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  UPDATE_SPLASH_CANCEL_SUFFIX,
  UPDATE_SPLASH_SCRIPT,
  UPDATE_SPLASH_TEMP_FILE,
  showUpdateSplash,
  splashArgs,
  splashCommandLine,
  windowsPowerShell,
} from '../../electron/updateSplash.mjs';

const SCRIPT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../electron');
const ENV = { SystemRoot: 'C:\\Windows' };
const PS = 'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe';

function fakeChild() {
  return { on: vi.fn(), unref: vi.fn() };
}

const logger = { info: vi.fn(), warn: vi.fn() };
let tmpDir = '';

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'nova-splash-'));
  logger.info.mockClear();
  logger.warn.mockClear();
});

afterEach(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe('the command that starts the window', () => {
  it('uses the inbox Windows PowerShell by full path', () => {
    expect(windowsPowerShell(ENV)).toBe(PS);
    expect(windowsPowerShell({})).toBe(PS);
  });

  it('passes the version, the process to wait for and the log, leaving out empty values', () => {
    const args = splashArgs('C:\\t\\w.ps1', { version: 'v976', processName: 'Nova', logPath: 'C:\\logs\\update.log' });
    expect(args.slice(args.indexOf('-File'))).toEqual([
      '-File', 'C:\\t\\w.ps1', '-ProcessName', 'Nova', '-Version', 'v976', '-LogPath', 'C:\\logs\\update.log',
    ]);
    expect(args).toContain('-NoProfile');
    expect(splashArgs('C:\\t\\w.ps1', { processName: 'Nova' })).not.toContain('-Version');
  });

  it('starts PowerShell minimized in a console of its own through cmd, quoting paths with spaces', () => {
    const line = splashCommandLine(PS, splashArgs('C:\\Users\\A B\\Temp\\w.ps1', { version: 'v976', processName: 'Nova' }));
    expect(line).toBe(
      '/d /s /c "start "" /min C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe -NoProfile -NoLogo '
        + '-ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\\Users\\A B\\Temp\\w.ps1" -ProcessName Nova -Version v976"',
    );
  });

  it('refuses a value cmd.exe would rewrite inside quotes', () => {
    expect(splashCommandLine(PS, ['-File', 'C:\\Users\\50%off\\w.ps1'])).toBeNull();
    expect(splashCommandLine(PS, ['-LogPath', 'C:\\a"b'])).toBeNull();
  });
});

describe('showUpdateSplash', () => {
  it('writes the script out of the app, clears a stale cancel, and starts cmd detached with no console of its own', () => {
    fs.writeFileSync(path.join(tmpDir, UPDATE_SPLASH_TEMP_FILE + UPDATE_SPLASH_CANCEL_SUFFIX), 'old');
    const child = fakeChild();
    const spawnFn = vi.fn(() => child);
    const handle = showUpdateSplash(
      { version: 'v976', processName: 'Nova', logger },
      { platform: 'win32', spawnFn: spawnFn as never, tmpDir, scriptDir: SCRIPT_DIR, env: ENV },
    );
    expect(handle).not.toBeNull();
    const scriptPath = path.join(tmpDir, UPDATE_SPLASH_TEMP_FILE);
    expect(fs.readFileSync(scriptPath, 'utf8')).toBe(fs.readFileSync(path.join(SCRIPT_DIR, UPDATE_SPLASH_SCRIPT), 'utf8'));
    expect(fs.existsSync(scriptPath + UPDATE_SPLASH_CANCEL_SUFFIX)).toBe(false);
    const [file, args, options] = spawnFn.mock.calls[0] as unknown as [string, string[], Record<string, unknown>];
    expect(file).toBe('C:\\Windows\\System32\\cmd.exe');
    expect(args).toHaveLength(1);
    expect(args[0]).toContain(`-File ${scriptPath.includes(' ') ? `"${scriptPath}"` : scriptPath}`);
    expect(options).toMatchObject({
      detached: true,
      stdio: 'ignore',
      windowsVerbatimArguments: true,
      cwd: tmpDir,
    });
    expect(child.unref).toHaveBeenCalled();
  });

  it('closes the window by writing the cancel file the script watches', () => {
    const handle = showUpdateSplash(
      { processName: 'Nova', logger },
      { platform: 'win32', spawnFn: vi.fn(fakeChild) as never, tmpDir, scriptDir: SCRIPT_DIR, env: ENV },
    );
    handle?.close();
    expect(fs.existsSync(path.join(tmpDir, UPDATE_SPLASH_TEMP_FILE + UPDATE_SPLASH_CANCEL_SUFFIX))).toBe(true);
  });

  it('is nothing off Windows, and a failure to start is logged, never thrown', () => {
    const spawnFn = vi.fn(() => {
      throw new Error('spawn EACCES');
    });
    expect(showUpdateSplash({ processName: 'Nova', logger }, { platform: 'darwin', spawnFn: spawnFn as never })).toBeNull();
    expect(spawnFn).not.toHaveBeenCalled();
    expect(
      showUpdateSplash(
        { processName: 'Nova', logger },
        { platform: 'win32', spawnFn: spawnFn as never, tmpDir, scriptDir: SCRIPT_DIR, env: ENV },
      ),
    ).toBeNull();
    expect(logger.warn).toHaveBeenCalledWith(expect.stringContaining('spawn EACCES'));
  });
});

describe('updateSplash.ps1', () => {
  const source = fs.readFileSync(path.join(SCRIPT_DIR, UPDATE_SPLASH_SCRIPT), 'utf8');

  it('is ASCII, because Windows PowerShell 5.1 reads a file without a BOM as ANSI', () => {
    expect([...source].filter((ch) => ch.charCodeAt(0) > 127)).toEqual([]);
  });

  it('declares every parameter the module passes, and watches the cancel file the module writes', () => {
    const passed = splashArgs('x.ps1', { version: 'v1', processName: 'Nova', logPath: 'l' })
      .filter((arg, i, all) => arg.startsWith('-') && all.indexOf('-File') < i)
      .map((arg) => arg.slice(1));
    const param = /param\(([\s\S]*?)\r?\n\)/.exec(source)?.[1] ?? '';
    expect(passed).toEqual(['ProcessName', 'Version', 'LogPath']);
    for (const name of passed) expect(param).toContain(`$${name}`);
    expect(source).toContain(`"$PSCommandPath${UPDATE_SPLASH_CANCEL_SUFFIX}"`);
  });
});
