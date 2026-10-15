/**
 * What a followed trader made over the span picked, in dollars as if each scored trade were copied with
 * `FT_STAKE_USD` (operator pick 2026-10-15: "Show the P/L as dollars at $1,000 a trade"; before it, the trades' %
 * added up, 2026-10-14 -- the same number over 100 times the stake). Under it a small line of that total trade by
 * trade, ending on the number. Their own dollars are unknown -- the feed never shows their size -- so the note says
 * the stake and the hover says why, with the average a trade. No scored trade is a dash with why, never $0.
 */
import { tipProps } from '../ux/hoverTip';
import { FT_PL_AT_STAKE, FT_PL_NO_SIZE, FT_STAKE_USD } from './constants';
import { DASH, signedPct, signedUsd } from './format';
import type { PlSummary } from './plSummary';

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`;
}

function leftOut(unscored: number): string {
  const parts = unscored > 0 ? [`${plural(unscored, 'unscored trade')} (no one exit price)`] : [];
  parts.push('open positions, until they close');
  return `Left out: ${parts.join(' and ')}.`;
}

/** The hover: what the number is, why it is per share, what it leaves out. */
export function plTip(s: PlSummary, unscored: number): string {
  if (s.count === 0) {
    return `No closed trade with one known exit price in this span, so nothing to add up. ${leftOut(unscored)}`;
  }
  return [
    `What copying ${plural(s.count, 'closed trade')} with $${FT_STAKE_USD.toLocaleString('en-US')} each would have made: `
      + `their own average in, the market price when it left their bar out (${signedPct(s.avgPct ?? 0)} a trade on `
      + 'average). The line is that total, trade by trade, oldest first.',
    FT_PL_NO_SIZE,
    leftOut(unscored),
  ].join('\n');
}

/** Percent points of the stake as dollars of it. */
function atStake(pct: number): number {
  return (pct / 100) * FT_STAKE_USD;
}

function tone(x: number): 'up' | 'down' | 'flat' {
  return x > 0 ? 'up' : x < 0 ? 'down' : 'flat';
}

/** The total after each trade, from 0, as a line over a dashed zero. */
function Spark({ curve, w, h }: { curve: number[]; w: number; h: number }) {
  const n = curve.length;
  if (n < 2) return null;
  const lo = Math.min(0, ...curve);
  const hi = Math.max(0, ...curve);
  const span = hi - lo || 1;
  const pad = 2.5;
  const x = (i: number) => pad + (i / (n - 1)) * (w - 2 * pad);
  const y = (v: number) => pad + (1 - (v - lo) / span) * (h - 2 * pad);
  const d = curve.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ');
  const last = curve[n - 1];
  return (
    <svg className={`ft-spark ft-spark--${tone(last)}`} width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      <line className="ft-spark__zero" x1={pad} x2={w - pad} y1={y(0)} y2={y(0)} />
      <path className="ft-spark__line" d={d} />
      <circle className="ft-spark__dot" cx={x(n - 1)} cy={y(last)} r={2.4} />
    </svg>
  );
}

interface Props {
  summary: PlSummary | null;
  /** Unscored trades in the span, said in the hover as left out. */
  unscored: number;
  /** Why there is no summary (the record still being read, an older backend); the dash's hover says it. */
  why?: string | null;
  /** In the head beside Everyone: on one line, a smaller line, "per share" in the hover only. */
  inline?: boolean;
  testId?: string;
}

export function PlFigure({ summary, unscored, why = null, inline = false, testId }: Props) {
  const cls = `ft-plfig${inline ? ' ft-plfig--inline' : ''}`;
  if (!summary || summary.count === 0) {
    return (
      <span className={`${cls} ft-plfig--none`} data-testid={testId} {...tipProps(summary ? plTip(summary, unscored) : why)}>
        <span className="ft-plfig__num ft-muted">{DASH}</span>
        {!inline && <span className="ft-plfig__note ft-muted">P/L {FT_PL_AT_STAKE}</span>}
      </span>
    );
  }
  return (
    <span className={`${cls} ft-plfig--${tone(summary.sumPct)}`} data-testid={testId} {...tipProps(plTip(summary, unscored))}>
      <span className="ft-plfig__num">{signedUsd(atStake(summary.sumPct))}</span>
      <Spark curve={summary.curve} w={inline ? 64 : 132} h={inline ? 18 : 28} />
      {!inline && <span className="ft-plfig__note ft-muted">{FT_PL_AT_STAKE} · {plural(summary.count, 'trade')}</span>}
    </span>
  );
}
