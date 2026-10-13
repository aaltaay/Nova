/**
 * The capture pill in the page's head: what the feed is doing right now, in the design's four states (live,
 * positions off screen, waiting for the stream, capture stopped) plus the feed itself not answering. Pure.
 */
import {
  FOLLOWED_CAPTURE_STALE_SEC,
  FT_BAD_ANSWER,
  FT_NO_STATUS,
  FT_PILL_HIDDEN,
  FT_PILL_STOPPED,
  FT_PILL_WAITING,
  FT_UNREACHABLE,
} from './constants';
import { duration } from './format';
import type { FollowedCapture, FollowedDay } from './types';

export type PillTone = 'live' | 'warn' | 'idle' | 'down';

export interface CapturePill {
  tone: PillTone;
  text: string;
}

const ET_SECONDS = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
});

function clockSec(clock: string): number | null {
  const m = /^(\d{1,2}):(\d{2}):(\d{2})$/.exec(clock);
  return m ? Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]) : null;
}

/** How far the bar's on-screen clock was behind the moment the feed read it, in seconds; null when unknown. */
export function behindStream(c: FollowedCapture): number | null {
  if (c.updated_at === null || !c.clock) return null;
  const read = clockSec(ET_SECONDS.format(new Date(c.updated_at * 1000)));
  const shown = clockSec(c.clock);
  if (read === null || shown === null) return null;
  const lag = read - shown;
  return lag >= 0 && lag < 3600 ? lag : null;
}

export function captureStopped(c: FollowedCapture): boolean {
  const stale = c.age_sec !== null && c.age_sec > FOLLOWED_CAPTURE_STALE_SEC;
  return stale || (c.problem !== null && (!c.live || c.updated_at === null));
}

export function capturePill(day: FollowedDay | null): CapturePill | null {
  if (!day) return null;
  if (day.feed.state === 'unreachable') return { tone: 'down', text: `${FT_UNREACHABLE} · ${day.feed.error ?? ''}` };
  if (day.feed.state === 'bad_answer') return { tone: 'down', text: `${FT_BAD_ANSWER} · ${day.feed.error ?? ''}` };
  const c = day.capture;
  if (!c) return { tone: 'idle', text: FT_NO_STATUS };
  if (captureStopped(c)) {
    const parts = [FT_PILL_STOPPED];
    if (c.clock) parts.push(`last read ${c.clock} ET`);
    else if (c.age_sec !== null) parts.push(`last read ${duration(c.age_sec)} ago`);
    if (c.problem) parts.push(c.problem);
    return { tone: 'down', text: parts.join(' · ') };
  }
  if (!c.live) return { tone: 'idle', text: FT_PILL_WAITING };
  if (!c.bar_visible) return { tone: 'warn', text: FT_PILL_HIDDEN };
  const parts = ['Live'];
  const lag = behindStream(c);
  if (lag !== null) parts.push(`${lag}s behind the stream`);
  if (c.clock) parts.push(`bar read ${c.clock} ET`);
  return { tone: 'live', text: parts.join(' · ') };
}
