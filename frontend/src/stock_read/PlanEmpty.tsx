/**
 * The plan box with no setup forming (ADR 036): plan a hand trade at 2:1 -- a long from the ask, a short from
 * the bid (ADR 048: its buy stop over the entry, its cover at entry - 2R), or a typed entry. A plan only: it
 * stages the ticket when asked and never sends.
 */
import { useState } from 'react';
import { whyProps } from '../ux';
import { fmtPx } from './planMath';
import type { StockReadContextValue } from './StockReadContext';
import type { StockRead } from './types';
import './shortRead.css';

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
      <span className="sr-plan__empty-why">{why} Plan a hand trade at 2:1:</span>
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
