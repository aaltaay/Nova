/**
 * `/api/ibkr/status` `auto_record` read at the boundary (ADR 023; the switch,
 * operator ask 2026-10-14). A malformed field becomes its empty value or is
 * left out -- never a guess: a switch that does not parse is absent, and
 * Records then says the switch is unavailable instead of drawing it On.
 */
import type { AutoRecordStatus, AutoRecordSwitch, AutoRecordWindow, AutoRecordWindows } from './types';

type Loose = Record<string, unknown>;

const isObject = (value: unknown): value is Loose =>
  value != null && typeof value === 'object' && !Array.isArray(value);
const text = (value: unknown): string | null => (typeof value === 'string' ? value : null);
const strings = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];

function stringMap(value: unknown): Record<string, string> | undefined {
  if (!isObject(value)) return undefined;
  const out: Record<string, string> = {};
  for (const [key, v] of Object.entries(value)) if (typeof v === 'string') out[key] = v;
  return out;
}

const OPEN = ['setups_and_leaders', 'setups', 'leaders', 'none'] as const;
const MODES = ['on', 'off_today', 'off'] as const;
const SOURCES = ['operator', 'env', 'default'] as const;

function window(value: unknown): AutoRecordWindow | null {
  if (!isObject(value)) return null;
  const setup = text(value.setup);
  const start = text(value.start);
  const end = text(value.end);
  return setup && start && end ? { setup, start, end, open: value.open === true } : null;
}

function windows(value: unknown): AutoRecordWindows | undefined {
  if (!isObject(value) || !isObject(value.setups) || !isObject(value.leaders)) return undefined;
  const open = OPEN.find(o => o === value.open);
  const leaders = value.leaders;
  const setups = value.setups;
  const lStart = text(leaders.start);
  const lEnd = text(leaders.end);
  if (!open || !lStart || !lEnd) return undefined;
  const bySetup = Array.isArray(setups.by_setup)
    ? setups.by_setup.map(window).filter((w): w is AutoRecordWindow => w != null) : [];
  return {
    open,
    setups: { open: setups.open === true, start: text(setups.start), end: text(setups.end), by_setup: bySetup,
      error: text(setups.error) },
    leaders: { open: leaders.open === true, start: lStart, end: lEnd },
  };
}

function autoSwitch(value: unknown): AutoRecordSwitch | undefined {
  if (!isObject(value)) return undefined;
  const mode = MODES.find(m => m === value.mode);
  const source = SOURCES.find(s => s === value.source);
  if (!mode || !source) return undefined;
  const until = typeof value.until === 'number' && Number.isFinite(value.until) ? value.until : null;
  return { mode, source, day: text(value.day), until, error: text(value.error) };
}

export function parseAutoRecordStatus(value: unknown): AutoRecordStatus | null {
  if (!isObject(value)) return null;
  const out: AutoRecordStatus = {
    active: value.active === true,
    window: text(value.window) ?? '',
    symbols: strings(value.symbols),
    yielded: strings(value.yielded),
    last_error: text(value.last_error),
  };
  const why = stringMap(value.why);
  const setup = stringMap(value.setup);
  const win = windows(value.windows);
  const sw = autoSwitch(value.switch);
  if (why) out.why = why;
  if (setup) out.setup = setup;
  if (win) out.windows = win;
  if (sw) out.switch = sw;
  return out;
}
