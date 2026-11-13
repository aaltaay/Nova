/**
 * Account, Calendar: the desk's Calendar panel on a phone (operator ask, 2026-11-13). One month of
 * weekday squares, each with the day's Net, Gross, Commissions or Trades; the tapped day's breakdown
 * sits under the month (a phone has no hover) and opens that day's chart on Overview. Every figure is
 * the desk's own (`account/accountCalendar`, `account/accountDayBreakdown`); the rows shrink to fit,
 * so the screen never scrolls.
 */
import { useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, LineChart } from 'lucide-react';
import { dayShortLabel, isoDate, monthGrid, monthLabel, parseIsoDate, shiftMonth } from '../../account/accountCalendar';
import { dayBreakdowns, monthDayTotals, type DayBreakdown } from '../../account/accountDayBreakdown';
import { todayPracticeDate } from '../../account/accountFigures';
import { monthSplit } from '../../account/ownerView';
import {
  ACCOUNT_CALENDAR_METRICS,
  accountFillCount,
  accountTradeCount,
  type AccountCalendarMetric,
} from '../../constantGroups/account_page';
import { phoneMonth } from '../phoneCalendar';
import { signedMoney, toneClass } from '../phoneFormat';
import type { PhoneAccount } from '../usePhoneAccount';

const METRIC_NAMES: Record<AccountCalendarMetric, string> = { net: 'Net', gross: 'Gross', commissions: 'Comm.', trades: 'Trades' };
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] as const;
/** A ledger reset mid-day: the day's net counts both ledgers, the line could only draw this one. */
const PART_ARCHIVED = 'Part of this day is in an archived ledger, which keeps totals only, so a chart would not match the day\'s net.';
const TOTALS_ONLY ='An archived ledger keeps only this day\'s totals, so there is no chart to draw.';

/** The figure one square shows, in whole dollars so it fits; null tone for a count. */
function squareFigure(metric: AccountCalendarMetric, day: DayBreakdown): { text: string; tone: string } {
  if (metric === 'trades') return { text: day.detailed ? String(day.trades.length) : '—', tone: '' };
  if (metric === 'commissions') return { text: signedMoney(-day.commissions, 0), tone: 'ph-muted' };
  const value = metric === 'gross' ? day.gross : day.net;
  return { text: signedMoney(value, 0), tone: toneClass(value) };
}

const countOf = (day: DayBreakdown): string => (day.detailed ? accountTradeCount(day.trades.length) : accountFillCount(day.fills));

function DayBox({ day, split, onChart }: {
  day: DayBreakdown | null;
  split: { you: number; bots: number } | null;
  onChart: (date: string) => void;
}) {
  if (!day) return <div className="ph-card ph-cal__day is-empty" role="status">Tap a day to see it.</div>;
  const movers = [...day.stocks].sort((a, b) => Math.abs(b.net) - Math.abs(a.net)).slice(0, 3).map((s) => s.symbol);
  return (
    <div className="ph-card ph-cal__day" data-testid="phone-calendar-day">
      <div className="ph-cal__day-head">
        <b>{dayShortLabel(day.date)}</b>
        <b className={toneClass(day.net)}>{signedMoney(day.net)}</b>
      </div>
      <div><span>Gross · costs</span><span>{signedMoney(day.gross)} · {signedMoney(-(day.commissions + day.fees))}</span></div>
      <div>
        <span>{day.detailed ? 'Trades' : 'Fills'}</span>
        <span>{day.detailed ? `${day.trades.length} · ${day.won} won, ${day.lost} lost` : day.fills}</span>
      </div>
      {split ? (
        <div><span>You · Bots</span><span>{signedMoney(split.you, 0)} · {signedMoney(split.bots, 0)}</span></div>
      ) : null}
      {day.detailed ? (
        <div><span>Stocks</span><span>{day.stocks.length}{movers.length ? ` · ${movers.join(', ')}` : ''}</span></div>
      ) : (
        <div><span className="ph-cal__note">Archived ledger: totals only.</span></div>
      )}
      <button
        type="button"
        className="ph-cal__chart"
        disabled={!day.detailed || day.partial}
        data-why={!day.detailed ? TOTALS_ONLY : day.partial ? PART_ARCHIVED : undefined}
        onClick={() => onChart(day.date)}
      >
        <LineChart size={13} aria-hidden /> See this day's chart
      </button>
    </div>
  );
}

export function AccountCalendar({ account, onChart }: { account: PhoneAccount; onChart: (date: string) => void }) {
  const today = todayPracticeDate(new Date(account.nowTs * 1000));
  const todayMonth = today.slice(0, 7);
  const [metric, setMetric] = useState<AccountCalendarMetric>('net');
  // A month browsed to holds until today's month moves (the desk's rule); a tapped day holds inside its month.
  const [browsed, setBrowsed] = useState<{ year: number; month: number; todayMonth: string } | null>(null);
  const [tapped, setTapped] = useState<string | null>(null);
  const start = parseIsoDate(today) ?? { year: 1970, month: 0, day: 1 };
  const month = browsed?.todayMonth === todayMonth ? browsed : start;
  const prefix = isoDate(month.year, month.month, 1).slice(0, 7);

  const history = account.calendar;
  const days = useMemo(() => (history ? dayBreakdowns(history) : null), [history]);
  const shown = useMemo(
    () => (history ? phoneMonth(monthGrid(month.year, month.month, history.daily, today)) : null),
    [history, month.year, month.month, today],
  );
  if (!history || !days || !shown) {
    return <div className="ph-empty ph-cal__absent" role="status" data-testid="phone-calendar-absent">{account.calendarAbsence}</div>;
  }

  const dates = shown.cells.flatMap((c) => (c.date ? [c.date] : []));
  const totals = monthDayTotals(days, dates);
  const traded = dates.filter((d) => days.has(d));
  // No day tapped in this month: today when it traded, else the month's last traded day.
  const selected = tapped?.startsWith(prefix) && days.has(tapped)
    ? tapped
    : days.has(today) && today.startsWith(prefix) ? today : traded[traded.length - 1] ?? null;
  const split = monthSplit(account.daySplits ? new Map(account.daySplits) : null, prefix);
  const total = metric === 'gross' ? totals.gross : metric === 'commissions' ? -totals.commissions : totals.net;
  const browse = (delta: number) => setBrowsed({ ...shiftMonth(month.year, month.month, delta), todayMonth });
  const names = shown.columns === 7 ? WEEKDAYS : WEEKDAYS.slice(1, 6);

  return (
    <div className="ph-cal" data-testid="phone-calendar">
      <div className="ph-cal__main">
        <div className="ph-cal__nav">
          <button type="button" aria-label="Previous month" onClick={() => browse(-1)}><ChevronLeft size={18} aria-hidden /></button>
          <b data-testid="phone-calendar-title">{monthLabel(month.year, month.month)}</b>
          <button type="button" aria-label="Next month" onClick={() => browse(1)}><ChevronRight size={18} aria-hidden /></button>
        </div>
        <div className="ph-seg ph-cal__metrics" role="group" aria-label="What each day shows">
          {ACCOUNT_CALENDAR_METRICS.map((m) => (
            <button key={m} type="button" aria-pressed={m === metric} onClick={() => setMetric(m)}>{METRIC_NAMES[m]}</button>
          ))}
        </div>
        <div className="ph-cal__wd" style={{ gridTemplateColumns: `repeat(${shown.columns}, minmax(0, 1fr))` }}>
          {names.map((n) => <span key={n}>{n}</span>)}
        </div>
        <div className="ph-cal__grid" data-cols={shown.columns} style={{ gridTemplateColumns: `repeat(${shown.columns}, minmax(0, 1fr))` }}>
          {shown.cells.map((cell, i) => {
            const day = cell.date ? days.get(cell.date) : undefined;
            if (!cell.date) return <span key={`blank-${i}`} />;
            if (!day) {
              return (
                <span key={cell.date} className={`ph-cal__d is-blank${cell.today ? ' is-today' : ''}`} data-testid={`phone-calendar-${cell.date}`}>
                  <i>{cell.day}</i>
                </span>
              );
            }
            const figure = squareFigure(metric, day);
            const date = cell.date;
            return (
              <button
                key={date}
                type="button"
                className={`ph-cal__d${cell.today ? ' is-today' : ''}${cell.archived ? ' is-arch' : ''}`}
                aria-pressed={date === selected}
                aria-label={`${dayShortLabel(date)} ${signedMoney(day.net)}`}
                data-testid={`phone-calendar-${date}`}
                onClick={() => setTapped(date)}
              >
                <i>{cell.day}</i>
                <b className={figure.tone}>{figure.text}</b>
                <u>{metric === 'trades' ? accountFillCount(day.fills) : countOf(day)}</u>
              </button>
            );
          })}
        </div>
        <div className="ph-cal__foot" data-testid="phone-calendar-foot">
          {metric === 'trades' ? (
            <span>Month <b>{accountTradeCount(totals.trades)}</b></span>
          ) : (
            <span>Month <b className={metric === 'commissions' ? '' : toneClass(total)}>{signedMoney(total)}</b></span>
          )}
          {metric === 'net' && split ? (
            <span>
              You <b className={toneClass(split.you)}>{signedMoney(split.you, 0)}</b> · Bots <b className={toneClass(split.bots)}>{signedMoney(split.bots, 0)}</b>
            </span>
          ) : (
            <span>{totals.won} won · {totals.lost} lost</span>
          )}
        </div>
      </div>
      <DayBox
        day={selected ? days.get(selected) ?? null : null}
        split={selected ? account.daySplits?.get(selected) ?? null : null}
        onChart={onChart}
      />
    </div>
  );
}
