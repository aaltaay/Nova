/**
 * The calendar under the day button: a month with a dot on each day the feed has, weekends dimmed, future days not
 * pickable (and saying why). Picking a day shows who traded what that day, read once without prices, before
 * "Open this day" opens it. Each square shows everyone's result that day and each row the trader's, copied at $1,000
 * a trade, from the record of every day (operator ask 2026-10-15: "the result of each for each day").
 */
import { useState } from 'react';
import { tipProps } from '../ux/hoverTip';
import { whyProps } from '../ux/whyTip';
import { dayLabel, monthCells, monthTitle, parseIso, shiftMonth, weekday } from './calendar';
import {
  FT_DAY_EMPTY,
  FT_DAY_EMPTY_WEEKEND,
  FT_FUTURE_DAY,
  FT_LOADING,
  FT_NEXT_MONTH,
  FT_OPEN_THIS_DAY,
  FT_PL_AT_STAKE,
  FT_PREV_MONTH,
  FT_STAKE_USD,
  FT_TODAY,
} from './constants';
import { shortUsd } from './format';
import { Face } from './parts';
import { PlFigure } from './PlFigure';
import { daysPl, type DaysPl, type PlSummary } from './plSummary';
import type { FollowedTrader } from './types';
import { useFollowedDay } from './useFollowedDay';
import { useFollowedRecord } from './useFollowedFetch';

const PREVIEW_EVERY_MS = 60_000;
const WEEK_HEAD = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];

export function tickersLine(trader: FollowedTrader): string {
  const counts = new Map<string, number>();
  for (const t of [...trader.closed].reverse().concat(trader.open)) counts.set(t.symbol, (counts.get(t.symbol) ?? 0) + 1);
  return [...counts].map(([sym, n]) => (n > 1 ? `${sym} ×${n}` : sym)).join(' · ');
}

/** A day's total as dollars of the stake. */
function dayUsd(s: PlSummary): number {
  return (s.sumPct / 100) * FT_STAKE_USD;
}

function tone(x: number): 'up' | 'down' | 'flat' {
  return x > 0 ? 'up' : x < 0 ? 'down' : 'flat';
}

function Preview({ date, pl, onOpen }: { date: string; pl: DaysPl; onOpen: (date: string) => void }) {
  const { data, error } = useFollowedDay(date, { quotes: false, everyMs: PREVIEW_EVERY_MS });
  const wd = weekday(date);
  let body;
  if (!data) body = <div className="ft-muted">{error ?? FT_LOADING}</div>;
  else if (data.feed.state !== 'ok') body = <div className="ft-muted">{data.feed.error}</div>;
  else if (data.traders.length === 0) {
    body = <div className="ft-empty">{wd === 0 || wd === 6 ? FT_DAY_EMPTY_WEEKEND : FT_DAY_EMPTY}</div>;
  } else {
    body = (
      <div className="ft-preview__list">
        {data.traders.map((t) => (
          <div key={t.name} className="ft-preview__row">
            <Face path={t.face} name={t.name} />
            <div className="ft-stack ft-min0">
              <span className="ft-strong">{t.name}</span>
              <span className="ft-mono ft-muted ft-small ft-ellipsis">{tickersLine(t)}</span>
            </div>
            <PlFigure summary={pl.why ? null : pl.of(date, t.name)} unscored={t.record.unscored} why={pl.why} inline
              testId={`ft-preview-pl-${t.name}`} />
            <span className="ft-pill-chip"><b>{t.open.length + t.closed.length}</b> trades</span>
            <span className="ft-pill-chip"><b>{t.open.length}</b> open</span>
          </div>
        ))}
        <button type="button" className="ft-primary" onClick={() => onOpen(date)} data-testid="ft-open-day">
          {FT_OPEN_THIS_DAY}
        </button>
      </div>
    );
  }
  return (
    <section className="ft-preview" aria-live="polite">
      <h2 className="ft-preview__title">{dayLabel(date)}</h2>
      {body}
    </section>
  );
}

interface Props {
  today: string;
  shown: string;
  dates: readonly string[];
  onOpen: (date: string | null) => void;
}

export function DayPicker({ today, shown, dates, onOpen }: Props) {
  const start = parseIso(shown);
  const [month, setMonth] = useState({ year: start.year, month: start.month });
  const [picked, setPicked] = useState<string>(shown);
  const records = useFollowedRecord('all', today);
  const pl = daysPl(records.data, records.error);
  const withTrades = new Set(dates);
  const cells = monthCells(month.year, month.month, { today, withTrades, picked });
  const t = parseIso(today);
  const atNewest = month.year === t.year && month.month === t.month;
  return (
    <div className="ft-picker" role="dialog" aria-label="Pick a day" data-testid="ft-day-picker">
      <section className="ft-calendar" aria-label={monthTitle(month.year, month.month)}>
        <div className="ft-calendar__head">
          <button type="button" className="ft-icon-btn" aria-label={FT_PREV_MONTH}
            onClick={() => setMonth(shiftMonth(month.year, month.month, -1))}>‹</button>
          <span className="ft-strong">{monthTitle(month.year, month.month)}</span>
          <button type="button" className="ft-icon-btn" aria-label={FT_NEXT_MONTH} disabled={atNewest}
            {...whyProps(atNewest, FT_FUTURE_DAY)} onClick={() => setMonth(shiftMonth(month.year, month.month, 1))}>›</button>
        </div>
        <div className="ft-calendar__grid ft-calendar__week">{WEEK_HEAD.map((d) => <span key={d}>{d}</span>)}</div>
        <div className="ft-calendar__grid">
          {cells.map((c, i) => {
            if (c === null) return <span key={`blank${i}`} />;
            const day = c.hasTrades ? pl.day(c.date) : null;
            const usd = day ? shortUsd(dayUsd(day)) : null;
            const tip = day ? `Everyone that day, ${FT_PL_AT_STAKE}: ${usd} over ${day.count} closed trade${day.count === 1 ? '' : 's'}` : null;
            return (
              <button key={c.date} type="button" disabled={c.future}
                {...(c.future ? whyProps(true, FT_FUTURE_DAY) : tipProps(tip))}
                aria-label={`${dayLabel(c.date)}${c.hasTrades ? ', has trades' : ''}${usd ? `, ${usd}` : ''}`}
                aria-pressed={c.picked}
                className={['ft-day', c.weekend && 'is-weekend', c.today && 'is-today', c.picked && 'is-picked',
                  c.hasTrades && 'has-trades'].filter(Boolean).join(' ')}
                onClick={() => setPicked(c.date)} data-testid={`ft-day-${c.date}`}>
                <span>{c.day}</span>
                {day && usd
                  ? <span className={`ft-day__pl ft-day__pl--${tone(dayUsd(day))}`} data-testid={`ft-day-pl-${c.date}`}>{usd}</span>
                  : <span className="ft-day__dot" aria-hidden="true" />}
              </button>
            );
          })}
        </div>
        <div className="ft-calendar__legend ft-small ft-muted">
          <span><span className="ft-day__dot ft-day__dot--legend" aria-hidden="true" />Has trades</span>
          <span>Weekends dimmed</span>
          <button type="button" className="ft-link" onClick={() => onOpen(null)}>{FT_TODAY}</button>
        </div>
      </section>
      <Preview date={picked} pl={pl} onOpen={(d) => onOpen(d === today ? null : d)} />
    </div>
  );
}
