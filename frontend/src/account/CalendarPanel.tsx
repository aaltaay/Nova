/**
 * Right middle -- Calendar of daily P&L from the history's `daily` rows.
 * Archived days are dimmed with a hollow dot, today is outlined, weekends
 * are "no session", and the footer sums archived against this ledger.
 *
 * It shows today's month, and moves with it: `today` is the venue's day, which
 * changes under a mounted panel -- Sim's clock answers after the first render
 * (until then the page reads the browser's), a replay of another day loads, the
 * venue switches. A month browsed to with ‹ › stays until today's month moves.
 *
 * Each day square shows Net, Gross, Commissions or Trades (the switch), with
 * the day's trade count under it; hovering a day opens its breakdown card and
 * clicking it opens the whole day on the page (operator ask, 2026-10-26).
 */
import { useState } from 'react';
import {
  ACCOUNT_CALENDAR_ARCHIVED,
  ACCOUNT_CALENDAR_BLANK,
  ACCOUNT_CALENDAR_EMPTY_MONTH,
  ACCOUNT_CALENDAR_METRICS,
  ACCOUNT_CALENDAR_METRIC_LABELS,
  ACCOUNT_CALENDAR_NEXT,
  ACCOUNT_CALENDAR_NO_SESSION,
  ACCOUNT_CALENDAR_PREV,
  ACCOUNT_CALENDAR_THIS_LEDGER,
  ACCOUNT_CALENDAR_TITLE,
  ACCOUNT_CALENDAR_UNDETAILED,
  ACCOUNT_CALENDAR_WEEKDAYS,
  accountCalendarCommFoot,
  accountCalendarGrossFoot,
  accountCalendarTradesFoot,
  accountFillCount,
  accountTradeCount,
  type AccountCalendarMetric,
} from '../constantGroups/account_page';
import { formatSignedMoney } from '../components/globalBarMoney';
import { formatMoney } from '../utils/formatMoney';
import { PanelHead, toneClass, toneOf, type Tone } from './accountBits';
import { dayLongLabel, monthGrid, monthLabel, parseIsoDate, shiftMonth } from './accountCalendar';
import { monthDayTotals, type DayBreakdown, type MonthDayTotals } from './accountDayBreakdown';
import type { PracticeHistory } from './accountHistoryTypes';
import { CalendarDayCard, type DayCardAnchor } from './CalendarDayCard';

interface Props {
  history: PracticeHistory | null;
  absence: string | null;
  /** Today's practice date, YYYY-MM-DD: the venue's day (Sim: the replay playhead's, C20 / V32). */
  today: string;
  /** The history's days broken down (accountDayBreakdown.dayBreakdowns). */
  days: ReadonlyMap<string, DayBreakdown> | null;
  /** The day open on the page, if any. */
  selected: string | null;
  /** A day clicked: open it, or close it when it is the one open. */
  onSelect: (date: string | null) => void;
}

/** A month browsed to, and the month today was in when it was. */
interface Browsed {
  year: number;
  month: number;
  todayMonth: string;
}

/** What one day square shows under the switch: its figure, that figure's tone, and the line under it. */
export function dayFigure(metric: AccountCalendarMetric, day: DayBreakdown): { value: string; tone: Tone; sub: string } {
  const count = day.detailed ? accountTradeCount(day.trades.length) : accountFillCount(day.fills);
  switch (metric) {
    case 'gross':
      return { value: formatSignedMoney(day.gross), tone: toneOf(day.gross), sub: count };
    case 'commissions':
      return { value: formatSignedMoney(-day.commissions), tone: 'muted', sub: count };
    case 'trades':
      return { value: day.detailed ? String(day.trades.length) : '—', tone: 'flat', sub: accountFillCount(day.fills) };
    default:
      return { value: formatSignedMoney(day.net), tone: toneOf(day.net), sub: count };
  }
}

function MetricFoot({ metric, totals }: { metric: Exclude<AccountCalendarMetric, 'net'>; totals: MonthDayTotals }) {
  const undetailed = totals.incompleteDays > 0 ? ` · ${ACCOUNT_CALENDAR_UNDETAILED}` : '';
  if (metric === 'gross') {
    return (
      <>
        {ACCOUNT_CALENDAR_METRIC_LABELS.gross} <b className={`acct-num ${toneClass(toneOf(totals.gross))}`}>{formatSignedMoney(totals.gross)}</b>{' '}
        {accountCalendarGrossFoot(formatSignedMoney(-totals.commissions), formatSignedMoney(-totals.fees))}
      </>
    );
  }
  if (metric === 'commissions') {
    const perTrade = totals.trades > 0 && totals.incompleteDays === 0 ? formatMoney(totals.commissions / totals.trades) : null;
    return (
      <>
        {ACCOUNT_CALENDAR_METRIC_LABELS.commissions} <b className="acct-num">{formatSignedMoney(-totals.commissions)}</b> · {accountCalendarCommFoot(formatSignedMoney(-totals.fees), perTrade)}
      </>
    );
  }
  return (
    <>
      <b className="acct-num">{accountTradeCount(totals.trades)}</b> · {accountCalendarTradesFoot(totals.fills, totals.won, totals.lost)}{undetailed}
    </>
  );
}

const anchorOf = (el: HTMLElement): DayCardAnchor => {
  const r = el.getBoundingClientRect();
  return { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
};

export function CalendarPanel({ history, absence, today, days, selected, onSelect }: Props) {
  const start = parseIsoDate(today) ?? { year: 1970, month: 0, day: 1 };
  const todayMonth = today.slice(0, 7);
  const [browsed, setBrowsed] = useState<Browsed | null>(null);
  const [metric, setMetric] = useState<AccountCalendarMetric>('net');
  const [hover, setHover] = useState<{ date: string; anchor: DayCardAnchor } | null>(null);
  const month = browsed?.todayMonth === todayMonth ? browsed : start;
  const browse = (delta: number) => setBrowsed({ ...shiftMonth(month.year, month.month, delta), todayMonth });
  const grid = history ? monthGrid(month.year, month.month, history.daily, today) : null;
  const archives = history?.archives.length ?? 0;
  const totals = grid && days ? monthDayTotals(days, grid.cells.flatMap((c) => (c.date ? [c.date] : []))) : null;
  const hovered = hover ? days?.get(hover.date) ?? null : null;

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
          <div className="acct-cal__bar">
            <div className="acct-seg" role="group" data-testid="account-calendar-metrics">
              {ACCOUNT_CALENDAR_METRICS.map((m) => (
                <button key={m} type="button" aria-pressed={metric === m} className={`acct-seg__item${metric === m ? ' is-on' : ''}`} data-testid={`account-calendar-metric-${m}`} onClick={() => setMetric(m)}>
                  {ACCOUNT_CALENDAR_METRIC_LABELS[m]}
                </button>
              ))}
            </div>
          </div>
          <div className="acct-cal" data-testid="account-calendar-grid">
            {ACCOUNT_CALENDAR_WEEKDAYS.map((wd) => <div key={wd} className="acct-cal__wd">{wd}</div>)}
            {grid.cells.map((cell, i) => {
              if (cell.day == null) return <div key={`blank-${i}`} className="acct-cal__d is-off" />;
              const cls = ['acct-cal__d'];
              if (cell.weekend) cls.push('is-off');
              if (cell.archived) cls.push('is-arch');
              if (cell.today) cls.push('is-today');
              const day = cell.date ? days?.get(cell.date) : undefined;
              if (!day || !cell.date) {
                return (
                  <div
                    key={cell.date}
                    className={cls.join(' ')}
                    data-testid={`account-calendar-day-${cell.date}`}
                    data-archived="false"
                    title={cell.weekend ? ACCOUNT_CALENDAR_NO_SESSION : undefined}
                  >
                    <span className="acct-cal__n">{cell.day}</span>
                  </div>
                );
              }
              const date = cell.date;
              const open = selected === date;
              if (open) cls.push('is-sel');
              const shown = dayFigure(metric, day);
              const show = (el: HTMLElement) => setHover({ date, anchor: anchorOf(el) });
              return (
                <button
                  key={date}
                  type="button"
                  className={cls.join(' ')}
                  data-testid={`account-calendar-day-${date}`}
                  data-archived={cell.archived ? 'true' : 'false'}
                  aria-pressed={open}
                  aria-label={`${dayLongLabel(date)} ${formatSignedMoney(day.net)}${cell.archived ? ` · ${ACCOUNT_CALENDAR_ARCHIVED}` : ''}`}
                  onClick={() => onSelect(open ? null : date)}
                  onMouseEnter={(e) => show(e.currentTarget)}
                  onMouseLeave={() => setHover(null)}
                  onFocus={(e) => show(e.currentTarget)}
                  onBlur={() => setHover(null)}
                >
                  <span className="acct-cal__n">{cell.day}</span>
                  <span className={`acct-cal__p acct-num ${toneClass(shown.tone)}`}>{shown.value}</span>
                  <span className="acct-cal__s">{shown.sub}</span>
                </button>
              );
            })}
          </div>
          <p className="acct-foot" data-testid="account-calendar-foot">
            {grid.rows === 0
              ? `${ACCOUNT_CALENDAR_EMPTY_MONTH} · ${ACCOUNT_CALENDAR_BLANK}`
              : metric !== 'net' && totals
                ? <><MetricFoot metric={metric} totals={totals} /> · {ACCOUNT_CALENDAR_BLANK}</>
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
      {hover && hovered && <CalendarDayCard day={hovered} anchor={hover.anchor} />}
    </section>
  );
}
