/**
 * The Calendar's hover card: one day's net taken apart -- gross, commissions,
 * SEC + FINRA fees -- and what was traded (operator ask, 2026-10-26). It
 * lives in a portal so the calendar panel's own scroll never cuts it, sits
 * under the day (above it near the screen's foot) and closes when the pointer
 * leaves the day. A day only an archived ledger traded shows its totals and
 * says why nothing more is listed.
 */
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import {
  ACCOUNT_COMP_COMMISSIONS,
  ACCOUNT_COMP_FEES,
  ACCOUNT_DAY_ARCHIVED_NOTE,
  ACCOUNT_DAY_CARD_GAP_PX,
  ACCOUNT_DAY_CARD_HINT,
  ACCOUNT_DAY_CARD_STOCKS,
  ACCOUNT_DAY_FILLS,
  ACCOUNT_DAY_GROSS,
  ACCOUNT_DAY_PARTIAL_NOTE,
  ACCOUNT_DAY_SHARES,
  ACCOUNT_DAY_STOCKS,
  ACCOUNT_DAY_TRADES,
  ACCOUNT_TRADE_DEFINITION,
  accountDayFillsBot,
  accountDayShares,
  accountDayStocks,
  accountDayWonLost,
} from '../constantGroups/account_page';
import { formatShareQty } from '../utils/formatShareQty';
import { Money } from './accountBits';
import { dayLongLabel } from './accountCalendar';
import type { DayBreakdown } from './accountDayBreakdown';

export interface DayCardAnchor {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/** Centred under the anchor (above it when the foot of the screen is too near), kept inside the viewport. */
export function dayCardPosition(
  anchor: DayCardAnchor,
  size: { width: number; height: number },
  viewport: { width: number; height: number },
  gap = ACCOUNT_DAY_CARD_GAP_PX,
): { left: number; top: number } {
  const centred = (anchor.left + anchor.right) / 2 - size.width / 2;
  const left = Math.max(gap, Math.min(centred, viewport.width - gap - size.width));
  const below = anchor.bottom + gap;
  const top = below + size.height <= viewport.height - gap ? below : Math.max(gap, anchor.top - gap - size.height);
  return { left, top };
}

/** The stocks that moved the day most, by the size of their net. */
const movers = (day: DayBreakdown): string[] =>
  [...day.stocks].sort((a, b) => Math.abs(b.net) - Math.abs(a.net)).slice(0, ACCOUNT_DAY_CARD_STOCKS).map((s) => s.symbol);

function Row({ k, children, title }: { k: string; children: ReactNode; title?: string }) {
  return (
    <div className="acct-day-card__row" title={title}>
      <span className="acct-muted">{k}</span>
      <span className="acct-num">{children}</span>
    </div>
  );
}

export function CalendarDayCard({ day, anchor }: { day: DayBreakdown; anchor: DayCardAnchor }) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();
    setPos(dayCardPosition(anchor, { width, height }, { width: window.innerWidth, height: window.innerHeight }));
  }, [anchor]);
  return createPortal(
    <div
      ref={ref}
      role="tooltip"
      className="acct-day-card"
      data-testid="account-calendar-card"
      style={pos ?? { left: anchor.left, top: anchor.bottom, visibility: 'hidden' }}
    >
      <div className="acct-day-card__head">
        <span>{dayLongLabel(day.date)}</span>
        <Money value={day.net} signed />
      </div>
      <Row k={ACCOUNT_DAY_GROSS}><Money value={day.gross} signed /></Row>
      <Row k={ACCOUNT_COMP_COMMISSIONS}><Money value={-day.commissions} signed kind="cost" /></Row>
      <Row k={ACCOUNT_COMP_FEES}><Money value={-day.fees} signed kind="cost" /></Row>
      <div className="acct-day-card__rule" />
      {day.detailed && (
        <Row k={ACCOUNT_DAY_TRADES} title={ACCOUNT_TRADE_DEFINITION}>
          {day.trades.length} · {accountDayWonLost(day.won, day.lost)}
        </Row>
      )}
      <Row k={ACCOUNT_DAY_FILLS}>{accountDayFillsBot(day.fills, day.botFills)}</Row>
      {day.detailed && (
        <>
          <Row k={ACCOUNT_DAY_SHARES}>{accountDayShares(formatShareQty(day.sharesBought), formatShareQty(day.sharesSold))}</Row>
          <Row k={ACCOUNT_DAY_STOCKS}>{accountDayStocks(day.stocks.length, movers(day))}</Row>
        </>
      )}
      {!day.detailed && <p className="acct-day-card__note">{ACCOUNT_DAY_ARCHIVED_NOTE}</p>}
      {day.partial && <p className="acct-day-card__note">{ACCOUNT_DAY_PARTIAL_NOTE}</p>}
      <p className="acct-day-card__hint">{ACCOUNT_DAY_CARD_HINT}</p>
    </div>,
    document.body,
  );
}
