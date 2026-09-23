/**
 * The in-app updater's log (#347). A packaged desk's main-process console goes
 * nowhere, so an update failure left no trace beyond one line in the Help menu
 * (2026-09-23). Each line goes to the console and to `update.log` in the app's
 * logs folder (`%APPDATA%\nova\logs`), which rolls to `update.log.1` past
 * UPDATE_LOG_MAX_BYTES. Writing never throws: a log that cannot be written
 * must not stop an update.
 */
import fs from 'node:fs';
import path from 'node:path';

export const UPDATE_LOG_FILE = 'update.log';
export const UPDATE_LOG_MAX_BYTES = 1_000_000;

/**
 * @param {{ prefix: string, dir: () => string, now?: () => Date }} opts
 *   `dir` is asked on every line, so a folder that appears later is used.
 */
export function createUpdateLogger({ prefix, dir, now = () => new Date() }) {
  let fileBroken = false;
  const toFile = (level, msg) => {
    if (fileBroken) return;
    try {
      const folder = dir();
      if (!folder) return;
      fs.mkdirSync(folder, { recursive: true });
      const file = path.join(folder, UPDATE_LOG_FILE);
      if (fs.existsSync(file) && fs.statSync(file).size > UPDATE_LOG_MAX_BYTES) {
        fs.renameSync(file, `${file}.1`);
      }
      fs.appendFileSync(file, `${now().toISOString()} ${level} ${msg}\n`);
    } catch (err) {
      fileBroken = true;
      console.warn(prefix, `update log unavailable: ${err instanceof Error ? err.message : String(err)}`);
    }
  };
  const line = (level, write) => (msg) => {
    const text = String(msg);
    write(prefix, text);
    toFile(level, text);
  };
  return {
    info: line('INFO', console.log),
    warn: line('WARN', console.warn),
    error: line('ERROR', console.error),
    debug: () => {},
  };
}
