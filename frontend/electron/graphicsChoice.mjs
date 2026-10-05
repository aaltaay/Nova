/**
 * Whether the desk draws with the graphics card (operator decision 2026-10-05, #707). Software drawing was
 * the Windows default from the 2026-09-17 black-window fix, which changed three things at once and never
 * tested the graphics card on its own; in software a chart drag ran at about 22 frames a second on the
 * desk's 4K monitor at 150%, and with the graphics card at 100 and more (measured in Electron 41 on the
 * demo desk). The graphics card is the default now, with a safety net (graphicsWatch.mjs) that turns it
 * off by itself.
 *
 * The choice lives in `graphics.json` in the app's userData:
 * `{schema_version: 1, gpu: "on" | "off", reason: "operator" | "gpu_crashed" | "blank_window", at: number
 * | null, detail: string | null, told: boolean}` -- `at` epoch seconds, `told` once the operator has been
 * told why it is off. No file draws with the graphics card. A file Nova cannot read, or of another
 * version, draws in software (the mode that was safe before) and says so. `NOVA_ELECTRON_GPU` (1 / 0)
 * still wins over the file.
 */
import fs from 'node:fs';
import path from 'node:path';

export const GRAPHICS_FILE = 'graphics.json';
export const GRAPHICS_SCHEMA_VERSION = 1;
export const GPU_ENV = 'NOVA_ELECTRON_GPU';
export const GRAPHICS_REASONS = ['operator', 'gpu_crashed', 'blank_window'];

const errText = (err) => (err instanceof Error ? err.message : String(err));

/** `NOVA_ELECTRON_GPU`: true / false when set to a yes or a no, null otherwise. */
export function envGpu(env = process.env) {
  const raw = String(env[GPU_ENV] ?? '').trim().toLowerCase();
  if (raw === '1' || raw === 'true' || raw === 'yes') return true;
  if (raw === '0' || raw === 'false' || raw === 'no') return false;
  return null;
}

/** A choice from the file's text, or why it is not one. */
export function parseChoice(text) {
  let v;
  try {
    v = JSON.parse(text);
  } catch (err) {
    return { choice: null, error: `not JSON (${errText(err)})` };
  }
  if (!v || typeof v !== 'object') return { choice: null, error: 'not an object' };
  if (v.schema_version !== GRAPHICS_SCHEMA_VERSION) {
    return { choice: null, error: `schema_version ${JSON.stringify(v.schema_version)} is not ${GRAPHICS_SCHEMA_VERSION}` };
  }
  if (v.gpu !== 'on' && v.gpu !== 'off') return { choice: null, error: `gpu ${JSON.stringify(v.gpu)} is not "on" or "off"` };
  return {
    choice: {
      schema_version: GRAPHICS_SCHEMA_VERSION,
      gpu: v.gpu,
      reason: GRAPHICS_REASONS.includes(v.reason) ? v.reason : 'operator',
      at: typeof v.at === 'number' && Number.isFinite(v.at) ? v.at : null,
      detail: typeof v.detail === 'string' ? v.detail : null,
      told: v.told === true,
    },
    error: null,
  };
}

/** The stored choice: `{choice, error}`, both null when there is no file. */
export function readChoice(dir, fsImpl = fs) {
  const file = path.join(dir, GRAPHICS_FILE);
  let text;
  try {
    text = fsImpl.readFileSync(file, 'utf8');
  } catch (err) {
    if (err?.code === 'ENOENT') return { choice: null, error: null };
    return { choice: null, error: `cannot read ${file}: ${errText(err)}` };
  }
  const parsed = parseChoice(text);
  return parsed.error ? { choice: null, error: `${file}: ${parsed.error}` } : parsed;
}

/** Store `choice` (through a temp file and a rename). */
export function writeChoice(dir, choice, fsImpl = fs) {
  const file = path.join(dir, GRAPHICS_FILE);
  const tmp = `${file}.tmp`;
  const body = {
    schema_version: GRAPHICS_SCHEMA_VERSION,
    gpu: choice.gpu,
    reason: choice.reason,
    at: choice.at ?? null,
    detail: choice.detail ?? null,
    told: choice.told === true,
  };
  fsImpl.mkdirSync(dir, { recursive: true });
  fsImpl.writeFileSync(tmp, `${JSON.stringify(body, null, 2)}\n`);
  fsImpl.renameSync(tmp, file);
}

/**
 * How this start draws: `{gpu, source: "env" | "choice" | "default" | "unreadable", choice, error}`.
 * `read` is `readChoice`'s answer.
 */
export function decideGraphics({ env = process.env, read = { choice: null, error: null } } = {}) {
  const forced = envGpu(env);
  if (forced !== null) return { gpu: forced, source: 'env', choice: read.choice, error: read.error };
  if (read.error) return { gpu: false, source: 'unreadable', choice: null, error: read.error };
  if (read.choice) return { gpu: read.choice.gpu === 'on', source: 'choice', choice: read.choice, error: null };
  return { gpu: true, source: 'default', choice: null, error: null };
}
