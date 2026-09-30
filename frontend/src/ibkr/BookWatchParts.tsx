/**
 * What left the book, drawn on the Level 2 ladder (ADR 033 amendment, 2026-09-29): each side's line of
 * the last minute above the book, and the marks between its rows -- what left the book, and since
 * 2026-09-30 the hidden sellers and buyers (bookWatchHidden.ts). The verdicts are the backend book
 * watcher's (bookWatch.ts reads them); every piece explains itself on hover.
 */
import { useEffect, useState } from 'react';
import { L2_PULLS_NOT_WATCHED_LABEL, L2_PULL_MARK_TICK_MS } from '../constants';
import { tipProps } from '../ux';
import { bookWatchBusy, pullsLine, type BookWatchState, type PullMark } from './bookWatch';

/**
 * The clock the marks age by: now, redrawn every L2_PULL_MARK_TICK_MS while a mark or tag is still due
 * to fade or go, so they leave on time on a quiet book (a busy one redraws with every book anyway).
 */
export function useBookWatchClock(watch: BookWatchState | null, active: boolean): number {
  const [, setTick] = useState(0);
  const busy = active && bookWatchBusy(watch, Date.now());
  useEffect(() => {
    if (!busy) return;
    const id = window.setInterval(() => setTick(t => t + 1), L2_PULL_MARK_TICK_MS);
    return () => window.clearInterval(id);
  }, [busy]);
  return Date.now();
}

/** Each side's size pulled against its size traded over the watcher's last minute, over its column. */
export function PullsStrip({ watch }: { watch: BookWatchState | null }) {
  const bid = pullsLine(watch, 'bid');
  const ask = pullsLine(watch, 'ask');
  if (!bid || !ask) return null;
  if (!bid.watching) {
    return (
      <div className="das-l2-pulls das-l2-pulls--absent" data-testid="l2-pulls" {...tipProps(bid.tip, 'Level 2 pulls')}>
        {L2_PULLS_NOT_WATCHED_LABEL}
      </div>
    );
  }
  return (
    <div className="das-l2-pulls" data-testid="l2-pulls">
      {([['bid', bid], ['ask', ask]] as const).map(([side, line]) => (
        <span
          key={side}
          className={`das-l2-pulls__side das-l2-pulls__side--${side}${line.warn ? ' das-l2-pulls__side--warn' : ''}`}
          data-testid={`l2-pulls-${side}`}
          {...tipProps(line.tip, line.title)}
        >
          <span className="das-l2-pulls__pulled">{line.pulled}</span>
          <span className="das-l2-pulls__traded">{line.traded}</span>
          {line.hidden && <span className="das-l2-pulls__hidden">{line.hidden}</span>}
        </span>
      ))}
    </div>
  );
}

/**
 * The marks at one place between the rows, drawn over the boundary like the plan's levels and taking no
 * height: a dashed line where the size was (solid when it was pulled as the price came closer) and a chip
 * per verdict. Above the book (`head`) the chips sit over the column head, with no line.
 */
export function PullMarksAt({ marks, at }: { marks: readonly PullMark[]; at: 'head' | 'edge' | 'end' }) {
  if (!marks.length) return null;
  const lead = marks.find(m => m.kind === 'approach') ?? marks.find(m => m.kind === 'pulled') ?? marks[0];
  return (
    <div
      className={`das-l2-pullmarks das-l2-pullmarks--${at} das-l2-pullmarks--${lead.kind}`}
      style={{ opacity: Math.max(...marks.map(m => m.opacity)) }}
    >
      {marks.map(m => (
        <span
          key={m.id}
          className={`das-l2-pullmark das-l2-pullmark--${m.kind}`}
          style={{ opacity: m.opacity / Math.max(...marks.map(x => x.opacity), 1e-6) }}
          data-testid={`l2-pullmark-${m.kind}`}
          {...tipProps(m.tip, m.title)}
        >
          {m.label}
        </span>
      ))}
    </div>
  );
}
