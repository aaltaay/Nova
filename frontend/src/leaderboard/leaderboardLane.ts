/**
 * Pure: the thin leaderboard lane under the Sim band -- where the Scanner
 * board was recorded (or rebuilt) on the desk's day, on the band's own scale
 * (the clock's session window, the same math as the recorded lane), and the
 * gaps between as gaps with their reason. Nothing is drawn until the coverage
 * for the clock's day has answered: an unknown is never drawn as "not recorded".
 */
import type { SimClockState } from '../sim/simClockTypes';
import { clockWindow } from '../sim/simStripFormat';
import {
  LEADERBOARD_LANE_GAP_WORD,
  LEADERBOARD_SOURCE_WORD,
  leaderboardLaneGapsTitle,
  leaderboardLaneTitle,
} from './leaderboardConstants';
import type { LeaderboardCoverage } from './leaderboardTypes';

export interface LeaderboardLaneSegment {
  left: number;
  width: number;
  kind: 'span' | 'gap';
  /** For a gap: why there is no board, and when. */
  title: string;
}

export interface LeaderboardLane {
  date: string;
  source: string | null;
  segments: LeaderboardLaneSegment[];
  title: string;
}

export function leaderboardLane(
  clock: SimClockState | null | undefined,
  coverage: LeaderboardCoverage | null | undefined,
  format: (epochSeconds: number) => string,
): LeaderboardLane | null {
  const window = clockWindow(clock);
  if (!window || !coverage || !clock?.session_date || coverage.date !== clock.session_date) return null;
  const { open, close } = window;
  const place = (a: number, b: number) => ({
    left: (Math.max(a, open) - open) / (close - open),
    width: (Math.min(b, close) - Math.max(a, open)) / (close - open),
  });
  const word = LEADERBOARD_SOURCE_WORD[coverage.source ?? ''] ?? 'recorded';
  const spans = coverage.spans.map(([a, b]) => ({ ...place(a, b), kind: 'span' as const, title: `${format(a)}–${format(b)}` }));
  const gaps = coverage.gaps.map(gap => ({
    ...place(gap.start, gap.end),
    kind: 'gap' as const,
    title: `${LEADERBOARD_LANE_GAP_WORD[gap.reason] ?? gap.reason} ${format(gap.start)}–${format(gap.end)}`,
  }));
  const segments = [...spans, ...gaps].filter(segment => segment.width > 0).sort((a, b) => a.left - b.left);
  const shownGaps = segments.filter(segment => segment.kind === 'gap').map(segment => segment.title);
  const ranges = segments.filter(segment => segment.kind === 'span').map(segment => segment.title).join(', ');
  const title = [
    leaderboardLaneTitle(word, ranges),
    shownGaps.length ? leaderboardLaneGapsTitle(shownGaps.join(', ')) : '',
  ].filter(Boolean).join('\n');
  return { date: coverage.date, source: coverage.source, segments, title };
}
