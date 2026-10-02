/**
 * Right middle -- Calendar of daily P&L from the history's `daily` rows.
 * Archived days are dimmed with a hollow dot, today is outlined, weekends
 * are "no session", and the footer sums archived against this ledger.
 *
 * It shows today's month, and moves with it: `today` is the venue's day, which
 * changes under a mounted panel -- Sim's clock answers after the first render
 * (until then the page reads the browser's), a replay of another day loads, the
 * venue switches. A month browsed to with ‹ › stays until today's month moves.
 */
import { useState } from 'react';
import {
  ACCOUNT_CALENDAR_ARCHIVED,
  ACCOUNT_CALENDAR_BLANK,
  ACCOUNT_CALENDAR_EMPTY_MONTH,
  ACCOUNT_CALENDAR_NEXT,
  ACCOUNT_CALENDAR_NO_SESSION,
  ACCOUNT_CALENDAR_PREV,
  ACCOUNT_CALENDAR_THIS_LEDGER,
  ACCOUNT_CALENDAR_TITLE,
  ACCOUNT_CALENDAR_WEEKDAYS,
} from '../constantGroups/account_page';
import { formatSignedMoney } from '../components/globalBarMoney';
import { PanelHead, toneClass, toneOf } from './accountBits';
import { monthGrid, monthLabel, parseIsoDate, shiftMonth } from './accountCalendar';
import type { PracticeHistory } from './accountHistoryTypes';

interface Props {
  history: PracticeHistory | null;
  absence: string | null;
  /** Today's practice date, YYYY-MM-DD: the venue's day (Sim: the replay playhead's, C20 / V32). */
  today: string;
}

/** A month browsed to, and the month today was in when it was. */
interface Browsed {
  year: number;
  month: number;
  todayMonth: string;
}

export function CalendarPanel({ history, absence, today }: Props) {
  const start = parseIsoDate(today) ?? { year: 1970, month: 0, day: 1 };
  const todayMonth = today.slice(0, 7);
  const [browsed, setBrowsed] = useState<Browsed | null>(null);
  const month = browsed?.todayMonth === todayMonth ? browsed : start;
  const browse = (delta: number) => setBrowsed({ ...shiftMonth(month.year, month.month, delta), todayMonth });
  const grid = history ? monthGrid(month.year, month.month, history.daily, today) : null;
  const archives = history?.archives.length ?? 0;

  return (
    <section className="acct-panel acct-panel--cal" data-testid="account-calendar" aria-label={ACCOUNT_CALENDAR_TITLE}>
      <PanelHead title={ACCOUNT_CALENDAR_TITLE}>
        <button type="button" className="acct-cal__nav" aria-label={ACCOUNT_CALENDAR_PREV} data-testid="account-calendar-prev" onClick={() => browse(-1)}>‹</button>
        <span className="acct-cal__title" data-testid="account-calendar-title">{monthLabel(month.year, month.month)}</span>
        <button type="button" className="acct-cal__nav" aria-label={ACCOUNT_CALENDAR_NEXT} data-testid="account-calendar-next" onClick={() => browse(1)}>›</button>
      </PanelHead>
      {!grid ? (
        <div className="acct-absent" data-testid="account-calendar-absent">{absence}</div>
      ) : (
        <>
          <div className="acct-cal" data-testid="account-calendar-grid">
            {ACCOUNT_CALENDAR_WEEKDAYS.map((wd) => <div key={wd} className="acct-cal__wd">{wd}</div>)}
            {grid.cells.map((cell, i) => {
              if (cell.day == null) return <div key={`blank-${i}`} className="acct-cal__d is-off" />;
              const cls = ['acct-cal__d'];
              if (cell.weekend) cls.push('is-off');
              if (cell.archived) cls.push('is-arch');
              if (cell.today) cls.push('is-today');
              return (
                <div
                  key={cell.date}
                  className={cls.join(' ')}
                  data-testid={`account-calendar-day-${cell.date}`}
                  data-archived={cell.archived ? 'true' : 'false'}
                  title={cell.pnl == null ? (cell.weekend ? ACCOUNT_CALENDAR_NO_SESSION : undefined) : `${cell.fills} fill${cell.fills === 1 ? '' : 's'}${cell.archived ? ` · ${ACCOUNT_CALENDAR_ARCHIVED}` : ''}`}
                >
                  <span className="acct-cal__n">{cell.day}</span>
                  {cell.pnl != null && (
                    <span className={`acct-cal__p acct-num ${toneClass(toneOf(cell.pnl))}`}>{formatSignedMoney(cell.pnl)}</span>
                  )}
                </div>
              );
            })}
          </div>
          <p className="acct-foot" data-testid="account-calendar-foot">
            {grid.rows === 0
              ? `${ACCOUNT_CALENDAR_EMPTY_MONTH} · ${ACCOUNT_CALENDAR_BLANK}`
              : (
                <>
                  {archives > 0 && (
                    <><i className="acct-dot-hollow" /> {ACCOUNT_CALENDAR_ARCHIVED} <b className={`acct-num ${toneClass(toneOf(grid.archivedTotal))}`}>{formatSignedMoney(grid.archivedTotal)}</b> · </>
                  )}
                  {ACCOUNT_CALENDAR_THIS_LEDGER} <b className={`acct-num ${toneClass(toneOf(grid.currentTotal))}`}>{formatSignedMoney(grid.currentTotal)}</b> · {ACCOUNT_CALENDAR_BLANK}
                </>
              )}
          </p>
        </>
      )}
    </section>
  );
}
