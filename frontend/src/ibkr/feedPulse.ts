/**
 * Is IBKR data arriving? `/api/ibkr/feed` (#672), and what the desk says about a gap.
 *
 * A gap is a stretch with no IBKR market data on any line after a busy one, while
 * IB Gateway is connected (the backend's `ibkr/feed_pulse.py` decides). On
 * 2026-10-01 the desk's Wi-Fi re-authenticated five times at the open; the charts
 * and Time & Sales froze for 4-16 s and the header read "STALE 0S". Pure.
 */
import {
  FEED_GAP_NO_DATA_LABEL,
  FEED_GAP_RECENT_LABEL,
  FEED_GAP_RECENT_SHOW_SEC,
  FEED_GAP_RECENT_TITLE_SUFFIX,
} from '../constantGroups/global_bar';

export interface FeedGap {
  start: number;
  end: number | null;
  silentSec: number;
  cause: 'wifi' | null;
  text: string;
}

export interface FeedPulse {
  now: number;
  gap: FeedGap | null;
  recent: FeedGap[];
}

export interface FeedGapBadge {
  tone: 'bad' | 'warn';
  state: 'no-data' | 'data-gap';
  label: string;
  title: string;
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function parseGap(raw: unknown): FeedGap | null {
  if (!raw || typeof raw !== 'object') return null;
  const g = raw as Record<string, unknown>;
  const start = num(g.start);
  const silentSec = num(g.silent_sec);
  if (start == null || silentSec == null) return null;
  return {
    start,
    end: num(g.end),
    silentSec,
    cause: g.cause === 'wifi' ? 'wifi' : null,
    text: typeof g.text === 'string' ? g.text : '',
  };
}

/** The route's answer, or null for anything this desk does not know (schema 1 only). */
export function parseFeedPulse(body: unknown): FeedPulse | null {
  if (!body || typeof body !== 'object') return null;
  const b = body as Record<string, unknown>;
  const now = num(b.now);
  if (b.schema_version !== 1 || now == null) return null;
  const recent = Array.isArray(b.recent)
    ? b.recent.map(parseGap).filter((g): g is FeedGap => g !== null && g.end != null)
    : [];
  return { now, gap: parseGap(b.gap), recent };
}

/**
 * NO DATA while a gap is open (red); DATA GAP for FEED_GAP_RECENT_SHOW_SEC after one
 * closed (amber); else nothing. `nowSec` is this desk's clock (the same PC).
 */
export function feedGapBadge(pulse: FeedPulse | null, nowSec: number): FeedGapBadge | null {
  if (!pulse) return null;
  if (pulse.gap) {
    const secs = Math.max(Math.floor(nowSec - pulse.gap.start), Math.floor(pulse.gap.silentSec));
    return { tone: 'bad', state: 'no-data', label: `${FEED_GAP_NO_DATA_LABEL} ${secs}s`, title: pulse.gap.text };
  }
  const last = pulse.recent[0];
  if (last?.end != null && nowSec - last.end <= FEED_GAP_RECENT_SHOW_SEC) {
    return {
      tone: 'warn',
      state: 'data-gap',
      label: `${FEED_GAP_RECENT_LABEL} ${Math.round(last.silentSec)}s`,
      title: `${last.text} ${FEED_GAP_RECENT_TITLE_SUFFIX}`.trim(),
    };
  }
  return null;
}
