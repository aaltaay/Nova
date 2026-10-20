/** Drop bars the as-of time has not closed yet. Same rule as tools/nova_review_causal.py. */

import type { RawBar } from '../tickerChartData';
import type { ReviewTf } from './reviewQuery';

const STEP_MS: Record<Exclude<ReviewTf, '1d'>, number> = {
  '1m': 60_000,
  '5m': 300_000,
  '10s': 10_000,
};

/** The session day's daily candle from minutes already closed. The official daily row can include later prints. */
export function sessionCandle(day: string, minutes: RawBar[]): RawBar | null {
  const session = minutes.filter((bar) => (
    bar.t.slice(0, 10) === day && bar.t.slice(11, 16) >= '04:00' && bar.t.slice(11, 16) < '16:00'
  ));
  if (!session.length) return null;
  return {
    t: day,
    o: session[0].o,
    h: Math.max(...session.map((bar) => bar.h)),
    l: Math.min(...session.map((bar) => bar.l)),
    c: session[session.length - 1].c,
    v: session.reduce((sum, bar) => sum + bar.v, 0),
  };
}

/** Prior days stay. The session day is the minutes closed by ``asOfIso``, not the official daily high. */
export function dailyAtCutoff(day: string, dailies: RawBar[], minutes: RawBar[], asOfIso: string): RawBar[] {
  const prior = cutBars(dailies, '1d', asOfIso).filter((bar) => bar.t.slice(0, 10) < day);
  const session = sessionCandle(day, cutBars(minutes, '1m', asOfIso));
  return session ? [...prior, session] : prior;
}

export function cutBars(bars: RawBar[], tf: ReviewTf, asOfIso: string): RawBar[] {
  if (tf === '1d') {
    const day = asOfIso.slice(0, 10);
    return bars.filter((bar) => bar.t.slice(0, 10) <= day);
  }
  const asOf = Date.parse(asOfIso);
  const step = STEP_MS[tf];
  if (!Number.isFinite(asOf)) return [];
  return bars.filter((bar) => {
    const start = Date.parse(bar.t);
    return Number.isFinite(start) && start + step <= asOf;
  });
}
