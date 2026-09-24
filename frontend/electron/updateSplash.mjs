/**
 * The "Updating Nova" window (updateSplash.ps1).
 *
 * The installer runs silently and Nova is closed while it does, so between the
 * operator's "Restart to update" and the new version's window nothing of Nova
 * was on screen -- 46 s on the desk PC on 2026-09-23, which read as "nothing
 * happened". Nova cannot draw that window itself, because the installer ends
 * every Nova.exe. A separate Windows PowerShell process shows it instead: it
 * outlives Nova, names the step it can see, and closes itself when the new
 * version's window is up.
 *
 * How it is started matters, and both obvious ways fail: a child spawned
 * `detached` gets no console and powershell.exe quits at once, and any other
 * child sits in libuv's kill-on-close job and dies with Nova. So cmd.exe is
 * started detached and `start /min` runs PowerShell with a console of its own
 * (which -WindowStyle Hidden then hides); a process started that way is in no job.
 *
 * Showing it never throws and never holds up an install. Without it the update
 * still installs, just in silence as before.
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { errorText } from './updatePolicy.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));

export const UPDATE_SPLASH_SCRIPT = 'updateSplash.ps1';
/** Where the script is written before it runs: PowerShell cannot read inside app.asar. */
export const UPDATE_SPLASH_TEMP_FILE = 'nova-update-window.ps1';
/** Written beside it to close the window when the install is called off (the script's own rule). */
export const UPDATE_SPLASH_CANCEL_SUFFIX = '.cancel';

function system32(env) {
  return path.win32.join(env.SystemRoot || env.windir || 'C:\\Windows', 'System32');
}

/** The inbox Windows PowerShell, by full path so nothing earlier on PATH stands in for it. */
export function windowsPowerShell(env = process.env) {
  return path.win32.join(system32(env), 'WindowsPowerShell', 'v1.0', 'powershell.exe');
}

/** @param {{ version?: string, processName: string, logPath?: string }} opts */
export function splashArgs(scriptPath, { version = '', processName, logPath = '' }) {
  const args = ['-NoProfile', '-NoLogo', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', scriptPath];
  args.push('-ProcessName', processName);
  // An empty value is left out rather than passed as "": the script has defaults.
  if (version) args.push('-Version', version);
  if (logPath) args.push('-LogPath', logPath);
  return args;
}

/**
 * cmd.exe's whole command line (passed verbatim): `start` the window's PowerShell
 * minimized, in its own console. Null when a value holds a character cmd would
 * read inside quotes (`"`, `%`) or a line break -- no window beats a wrong command.
 */
export function splashCommandLine(powershell, args) {
  const parts = [powershell, ...args];
  if (parts.some((part) => /["%\r\n]/.test(part))) return null;
  const quoted = parts.map((part) => (/[\s&|<>^()]/.test(part) ? `"${part}"` : part));
  return `/d /s /c "start "" /min ${quoted.join(' ')}"`;
}

/**
 * Show the window. Windows only; anything else, or any failure, is null.
 * @param {{ version?: string, processName: string, logPath?: string,
 *   logger: { info: (m: string) => void, warn: (m: string) => void } }} opts
 * @param {{ platform?: string, spawnFn?: typeof spawn, tmpDir?: string,
 *   scriptDir?: string, env?: NodeJS.ProcessEnv }} [deps]
 * @returns {{ close: () => void } | null}
 */
export function showUpdateSplash(opts, deps = {}) {
  const { logger } = opts;
  const {
    platform = process.platform,
    spawnFn = spawn,
    tmpDir = os.tmpdir(),
    scriptDir = HERE,
    env = process.env,
  } = deps;
  if (platform !== 'win32') return null;
  try {
    const scriptPath = path.join(tmpDir, UPDATE_SPLASH_TEMP_FILE);
    const cancelPath = `${scriptPath}${UPDATE_SPLASH_CANCEL_SUFFIX}`;
    const commandLine = splashCommandLine(windowsPowerShell(env), splashArgs(scriptPath, opts));
    if (!commandLine) {
      logger.warn('update window skipped: a path holds a character cmd.exe would rewrite');
      return null;
    }
    // Electron's fs reads inside app.asar; PowerShell gets a plain copy.
    fs.writeFileSync(scriptPath, fs.readFileSync(path.join(scriptDir, UPDATE_SPLASH_SCRIPT), 'utf8'), 'utf8');
    fs.rmSync(cancelPath, { force: true });
    const child = spawnFn(path.win32.join(system32(env), 'cmd.exe'), [commandLine], {
      detached: true,
      stdio: 'ignore',
      windowsHide: true,
      windowsVerbatimArguments: true,
      // Never the install folder, which the installer rewrites.
      cwd: tmpDir,
    });
    child.on('error', (err) => logger.warn(`update window failed: ${errorText(err)}`));
    child.unref();
    logger.info('showing the update window while the installer runs');
    return {
      close() {
        try {
          fs.writeFileSync(cancelPath, 'install called off\n');
        } catch (err) {
          logger.warn(`cannot close the update window: ${errorText(err)}`);
        }
      },
    };
  } catch (err) {
    logger.warn(`update window unavailable: ${errorText(err)}`);
    return null;
  }
}
