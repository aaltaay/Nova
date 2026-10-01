import { describe, expect, it } from 'vitest';
import { feedGapBadge, parseFeedPulse } from './feedPulse';

const T0 = 1_790_861_526; // 2026-10-01 09:32:06 ET

function body(over: Record<string, unknown> = {}) {
  return { schema_version: 1, now: T0 + 9, connected: true, gap: null, recent: [], ...over };
}

const open = { start: T0, end: null, silent_sec: 9.2, ongoing: true, cause: 'wifi', text: 'No IBKR data on any line for 9 s.' };
const closed = { start: T0, end: T0 + 16, silent_sec: 16.0, ongoing: false, cause: null, text: 'No IBKR data for 16 s.' };

describe('feed pulse (#672)', () => {
  it('reads schema 1 and refuses anything else', () => {
    expect(parseFeedPulse(body())).toEqual({ now: T0 + 9, gap: null, recent: [] });
    expect(parseFeedPulse({ ...body(), schema_version: 2 })).toBeNull();
    expect(parseFeedPulse(null)).toBeNull();
    expect(parseFeedPulse(body({ recent: [closed, { start: 'x' }] }))?.recent).toHaveLength(1);
  });

  it('is red NO DATA while a gap is open, counting on this desk\'s clock', () => {
    const badge = feedGapBadge(parseFeedPulse(body({ gap: open })), T0 + 11.4);
    expect(badge).toEqual({ tone: 'bad', state: 'no-data', label: 'NO DATA 11s', title: open.text });
  });

  it('is amber DATA GAP for a minute after one closed, then nothing', () => {
    const pulse = parseFeedPulse(body({ recent: [closed] }));
    const badge = feedGapBadge(pulse, T0 + 30);
    expect(badge).toMatchObject({ tone: 'warn', state: 'data-gap', label: 'DATA GAP 16s' });
    expect(badge?.title).toContain('No IBKR data for 16 s.');
    expect(badge?.title).toContain('then the held prints at the moment data came back');
    expect(feedGapBadge(pulse, T0 + 16 + 61)).toBeNull();
  });

  it('says nothing while data arrives or the route did not answer', () => {
    expect(feedGapBadge(parseFeedPulse(body()), T0)).toBeNull();
    expect(feedGapBadge(null, T0)).toBeNull();
  });
});
