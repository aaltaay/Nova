/**
 * Long animation frames for this window's performance report (ADR 026): how
 * often the main thread held a frame past 50 ms, how long it blocked input,
 * and which scripts used the time. Chromium's `long-animation-frame` entries
 * name each script (`scripts[]`); where they are unsupported the `longtask`
 * entries still give count and blocking time, with no script named.
 *
 * `top` ranks scripts by their total time inside long frames this interval,
 * keyed by function, file and invoker -- a handler that costs 60 ms forty
 * times outranks one 200 ms hitch.
 */
import {
  PERF_LONG_FRAME_SCRIPTS_MAX,
  PERF_LONG_FRAME_TOP,
  PERF_LONGTASK_BUDGET_MS,
  PERF_MAX_NAME_CHARS,
} from '../constantGroups/perf';

export const LOAF_ENTRY_TYPE = 'long-animation-frame';
export const LONGTASK_ENTRY_TYPE = 'longtask';

export interface LongFrameScriptTally {
  source: string;
  invoker: string;
  ms: number;
}

export interface LongFramesReport {
  count: number;
  blocking_ms: number;
  max_ms: number;
  top: LongFrameScriptTally[];
}

/** The fields read from a `PerformanceScriptTiming` (LoAF `scripts[]`). */
export interface LongFrameScript {
  duration: number;
  invoker?: string;
  sourceFunctionName?: string;
  sourceURL?: string;
}

/** The fields read from a `long-animation-frame` or `longtask` entry. */
export interface LongFrameEntry {
  entryType: string;
  duration: number;
  blockingDuration?: number;
  scripts?: readonly LongFrameScript[];
}

export interface LongFrameMeter {
  /** This interval's tally, then zero; null when the browser reports neither entry type. */
  take: () => LongFramesReport | null;
  stop: () => void;
}

const round1 = (ms: number) => Math.round(ms * 10) / 10;
const clip = (text: string) => text.slice(0, PERF_MAX_NAME_CHARS);

/** File name of a script URL, without path, query or hash. */
export function basename(url: string | undefined): string {
  const path = String(url ?? '').split(/[?#]/, 1)[0];
  return path.slice(path.lastIndexOf('/') + 1);
}

export function scriptSource(script: LongFrameScript): string {
  const file = basename(script.sourceURL) || '(unknown)';
  return `${script.sourceFunctionName || '(anonymous)'} @ ${file}`;
}

export function createLongFrameTally() {
  let count = 0;
  let blocking = 0;
  let max = 0;
  const scripts = new Map<string, LongFrameScriptTally>();

  function addScript(script: LongFrameScript): void {
    const source = clip(scriptSource(script));
    const invoker = clip(String(script.invoker ?? ''));
    const key = `${source}\n${invoker}`;
    const slot = scripts.get(key);
    if (slot) slot.ms += script.duration;
    else if (scripts.size < PERF_LONG_FRAME_SCRIPTS_MAX) {
      scripts.set(key, { source, invoker, ms: script.duration });
    }
  }

  return {
    add(entry: LongFrameEntry): void {
      count += 1;
      max = Math.max(max, entry.duration);
      blocking += entry.entryType === LOAF_ENTRY_TYPE
        ? entry.blockingDuration ?? 0
        : Math.max(0, entry.duration - PERF_LONGTASK_BUDGET_MS);
      for (const script of entry.scripts ?? []) addScript(script);
    },
    take(): LongFramesReport {
      const top = [...scripts.values()]
        .sort((a, b) => b.ms - a.ms)
        .slice(0, PERF_LONG_FRAME_TOP)
        .map((s) => ({ source: s.source, invoker: s.invoker, ms: round1(s.ms) }));
      const report = { count, blocking_ms: round1(blocking), max_ms: round1(max), top };
      count = 0;
      blocking = 0;
      max = 0;
      scripts.clear();
      return report;
    },
  };
}

/** The entry type this browser can observe, LoAF first. */
export function longFrameEntryType(
  supported: readonly string[] | undefined = typeof PerformanceObserver === 'undefined'
    ? undefined
    : PerformanceObserver.supportedEntryTypes,
): string | null {
  if (!supported) return null;
  if (supported.includes(LOAF_ENTRY_TYPE)) return LOAF_ENTRY_TYPE;
  if (supported.includes(LONGTASK_ENTRY_TYPE)) return LONGTASK_ENTRY_TYPE;
  return null;
}

const UNSUPPORTED: LongFrameMeter = { take: () => null, stop: () => {} };

export function startLongFrames(): LongFrameMeter {
  const type = longFrameEntryType();
  if (!type) return UNSUPPORTED;
  const tally = createLongFrameTally();
  try {
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) tally.add(entry as unknown as LongFrameEntry);
    });
    observer.observe({ type, buffered: false });
    return { take: () => tally.take(), stop: () => observer.disconnect() };
  } catch (err) {
    console.debug('[Nova] perf: long-frame observer unavailable', err);
    return UNSUPPORTED;
  }
}
