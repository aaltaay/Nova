/**
 * The Following page's layout rules, pure: who is shown and in what order (roster), what a fit level folds (fit),
 * and the stream's links (stream).
 */
import { describe, expect, it } from 'vitest';
import { fitPlan, maxFitLevel } from './fit';
import { day } from './followedTestData';
import { roster } from './roster';
import { embedUrl, playerCommand, streamId, watchUrl } from './stream';

describe('roster', () => {
  it('shows the bar in its order, then whoever else traded; a past day only those who traded', () => {
    const d = day();
    d.capture!.bar = [{ trader: 'BRAVO', positions: [], image: null, face: '/f/BRAVO.jpg' },
      { trader: 'CHARLIE', positions: [], image: null, face: '/f/CHARLIE.jpg' }];
    const today = roster(d, true);
    expect(today.map((e) => e.name)).toEqual(['BRAVO', 'CHARLIE', 'ALPHA']);
    // BRAVO's day has no photo: the bar slot's stands in. ALPHA, off the bar, keeps the day's.
    expect(today.map((e) => e.face)).toEqual(['/f/BRAVO.jpg', '/f/CHARLIE.jpg', '/api/followed-traders/faces/2026-10-13/ALPHA.jpg']);
    expect(today[1].trader).toBeNull();
    expect(roster(d, false).map((e) => e.name)).toEqual(['ALPHA', 'BRAVO']);
  });
});

describe('fit', () => {
  it('shrinks closed rows first, then folds the oldest from whoever shows the most', () => {
    const closed: [string, number][] = [['ALPHA', 5], ['BRAVO', 2], ['CHARLIE', 0]];
    expect(fitPlan(0, closed)).toEqual({ compact: false, folded: {} });
    expect(fitPlan(1, closed)).toEqual({ compact: true, folded: {} });
    expect(fitPlan(4, closed).folded).toEqual({ ALPHA: 3 });
    expect(fitPlan(6, closed).folded).toEqual({ ALPHA: 4, BRAVO: 1 });
    expect(maxFitLevel(closed)).toBe(8);
    expect(fitPlan(8, closed).folded).toEqual({ ALPHA: 5, BRAVO: 2 });
    expect(fitPlan(20, closed).folded).toEqual({ ALPHA: 5, BRAVO: 2 });
  });
});

describe('stream', () => {
  it('builds links only from a YouTube video id', () => {
    expect(streamId('R5YIugCJar0')).toBe('R5YIugCJar0');
    expect(streamId('x')).toBeNull();
    expect(streamId('R5YIugCJar0"><script>')).toBeNull();
    expect(streamId(undefined)).toBeNull();
    expect(embedUrl('R5YIugCJar0')).toMatch(/^https:\/\/www\.youtube-nocookie\.com\/embed\/R5YIugCJar0\?autoplay=1&mute=1&/);
    expect(watchUrl('R5YIugCJar0')).toBe('https://www.youtube.com/watch?v=R5YIugCJar0');
    expect(JSON.parse(playerCommand('unMute'))).toEqual({ event: 'command', func: 'unMute', args: [] });
  });
});
