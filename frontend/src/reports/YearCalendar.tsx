/**
 * Year grid of 12 month mini-calendars with daily P&L coloring. On Paper's All view each month lists the four books
 * under its total, and a day keeps one total with the traders who traded it in its tooltip (ADR 072, mockup
 * three-books v1: "the twelve small months keep one total a day").
 */
import type { CalendarDay, CalendarMonthSummary } from './types';
import { DOW_LABELS, MONTH_NAMES, fmtPnlShort } from './format';
import { pnlSplit, splitWords, tradedBooks } from './reportsView';
import { SplitLine } from './SplitLine';

interface Props {
  months: CalendarMonthSummary[];
  year: number;
  openMonth: number | null;
  onOpenMonth: (month: number) => void;
}

function dayMap(days: CalendarDay[]): Map<string, CalendarDay> {
  const map = new Map<string, CalendarDay>();
  for (const d of days) map.set(d.date, d);
  return map;
}

function MiniMonth({
  month,
  year,
  isOpen,
  onOpen,
}: {
  month: CalendarMonthSummary;
  year: number;
  isOpen: boolean;
  onOpen: () => void;
}) {
  const byDate = dayMap(month.days);
  const first = new Date(year, month.month - 1, 1);
  const startPad = (first.getDay() + 7) % 7; // Sun=0
  const daysInMonth = new Date(year, month.month, 0).getDate();
  const cells: Array<{ key: string; dayNum: number | null; data: CalendarDay | null }> = [];

  for (let i = 0; i < startPad; i++) {
    cells.push({ key: `pad-${i}`, dayNum: null, data: null });
  }
  for (let d = 1; d <= daysInMonth; d++) {
    const iso = `${year}-${String(month.month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    cells.push({ key: iso, dayNum: d, data: byDate.get(iso) ?? null });
  }

  return (
    <div className={`reports-month-card ${isOpen ? 'reports-month-open' : ''}`}>
      <div className="reports-month-card-head">
        <span className="reports-month-card-title">
          {MONTH_NAMES[month.month - 1]}, {year}
        </span>
        <button type="button" className="reports-month-open-btn" onClick={onOpen}>
          {isOpen ? 'Active' : 'Open'}
        </button>
      </div>
      <div className="reports-month-card-pnl" title="Net P/L for this month (CommissionReport subtracted when present)">
        {fmtPnlShort(month.pnl)}
        <span className="reports-month-card-trades"> · {month.trade_count} trades</span>
      </div>
      {month.trade_count > 0 && <SplitLine split={pnlSplit(month.by_owner, fmtPnlShort)} />}
      <div className="reports-mini-dow">
        {DOW_LABELS.map(l => (
          <span key={l}>{l}</span>
        ))}
      </div>
      <div className="reports-mini-grid">
        {cells.map(cell => {
          if (cell.dayNum == null) {
            return <div key={cell.key} className="reports-mini-cell reports-mini-pad" />;
          }
          const result = cell.data?.result;
          const cls = [
            'reports-mini-cell',
            result === 'win' ? 'reports-day-win' : '',
            result === 'loss' ? 'reports-day-loss' : '',
            cell.data && cell.data.trade_count > 0 ? 'reports-day-active' : '',
          ]
            .filter(Boolean)
            .join(' ');
          return (
            <div
              key={cell.key}
              className={cls}
              title={
                cell.data
                  ? [
                      `${cell.data.date}: ${fmtPnlShort(cell.data.pnl)} (${cell.data.trade_count} trades)`,
                      splitWords(pnlSplit(cell.data.by_owner, fmtPnlShort), tradedBooks(cell.data.by_owner)),
                    ].filter(Boolean).join(' · ')
                  : undefined
              }
            >
              <span className="reports-mini-daynum">{cell.dayNum}</span>
              {cell.data && cell.data.trade_count > 0 && (
                <span className="reports-mini-pnl">{fmtPnlShort(cell.data.pnl)}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function YearCalendar({ months, year, openMonth, onOpenMonth }: Props) {
  return (
    <div className="reports-year-grid">
      {months.map(m => (
        <MiniMonth
          key={m.month}
          month={m}
          year={year}
          isOpen={openMonth === m.month}
          onOpen={() => onOpenMonth(m.month)}
        />
      ))}
    </div>
  );
}
