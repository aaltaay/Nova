/**
 * The plan box with no setup forming (ADR 036): plan a hand trade -- a long from the ask, a short from the bid
 * (ADR 048: its buy stop over the entry, its covers under it), or a typed entry -- with the target menu's defaults
 * (#845: target 1 at 20c or a half / whole dollar, target 2 at the high of day or the next level), which the backend
 * reads from the entry and today's levels. A plan only: it stages the ticket when asked and never sends.
 */
import { useState } from 'react';
import { tipProps, whyProps } from '../ux';
import { fmtPx } from './planMath';
import type { StockReadContextValue } from './StockReadContext';
import type { StockRead } from './types';
import './shortRead.css';

const EMPTY_PLAN_TIP = 'Your entry, your stop (or the last candles\' low), and the target menu\'s defaults: target 1 '
  + '20c past the entry, or 1c before a half / whole dollar when that is closer; target 2 1c before the high of day, '
  + 'else 1c before the next level of today\'s map; half at each. A short mirrors it under the entry.';

export function EmptyPlan({ ctx, read }: { ctx: StockReadContextValue; read: StockRead }) {
  const ask = ctx.topOfBook?.ask ?? null;
  const bid = ctx.topOfBook?.bid ?? null;
  const [text, setText] = useState('');
  const commit = () => {
    const n = Number(text.replace(/[$,\s]/g, ''));
    if (Number.isFinite(n) && n > 0) ctx.setManualPlan(n, null, 'long');
  };
  const why = read.followed ? 'No setup is forming on it.' : (read.followed_note ?? 'The setup scanner does not follow it.');
  return (
    <div className="sr-plan__empty" data-testid="stock-read-plan-empty">
      <span className="sr-plan__empty-why" {...tipProps(EMPTY_PLAN_TIP, 'Plan a hand trade')}>
        {why} Plan a hand trade with the menu's targets:
      </span>
      <button
        type="button"
        className="sr-btn"
        disabled={ask === null}
        {...whyProps(ask === null, 'No ask on Level 2 yet.')}
        onClick={() => ask !== null && ctx.setManualPlan(ask, null, 'long')}
        data-testid="stock-read-entry-ask"
      >
        Entry at the ask {ask === null ? '' : fmtPx(ask)}
      </button>
      <button
        type="button"
        className="sr-btn sr-btn--short"
        disabled={bid === null}
        {...whyProps(bid === null, 'No bid on Level 2 yet.')}
        onClick={() => bid !== null && ctx.setManualPlan(bid, null, 'short')}
        data-testid="stock-read-short-bid"
      >
        Short at the bid {bid === null ? '' : fmtPx(bid)}
      </button>
      <input
        className="sr-num__input sr-plan__empty-input"
        inputMode="decimal"
        aria-label="Your entry"
        placeholder="or type an entry"
        value={text}
        onChange={e => setText(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter') commit();
          e.stopPropagation();
        }}
        onBlur={commit}
        data-testid="stock-read-entry-type"
      />
    </div>
  );
}
