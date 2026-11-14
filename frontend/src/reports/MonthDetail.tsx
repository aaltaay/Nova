/**
 * Expanded month view: daily P&L cells + week totals (TraderVue-style). Paper's All view adds the four books (ADR
 * 072, mockup three-books v1): a day's cell lists only the traders who closed a trade that day; the month line and
 * the week column always list all four, in the books' order.
 */
import type { CalendarDay, MonthCalendarResponse } from './types';
import { DOW_LABELS, MONTH_NAMES, fmtPnl, fmtPnlShort } from './format';
import { pnlSplit, tradedBooks } from './reportsView';
import { SplitLine } from './SplitLine';

interface Props {
  data: MonthCalendarResponse;
  onClose: () => void;
}

function dayMap(days: CalendarDay[]): Map<string, CalendarDay> {
  const map = new Map<string, CalendarDay>();
  for (const d of days) map.set(d.date, d);
  return map;
}

function parseIso(iso: string): { year: number; month: number; day: number } {
  const [y, m, d] = iso.split('-').map(Number);
  return { year: y, month: m, day: d };
}

export function MonthDetail({ data, onClose }: Props) {
  const byDate = dayMap(data.days);

  return (
    <div className="reports-month-detail">
      <div className="reports-month-detail-head">
        <h2>
          {MONTH_NAMES[data.month - 1]}, {data.year}
        </h2>
        <div className="reports-month-detail-meta">
          <span>
            Monthly P&amp;L:{' '}
            <strong className={data.pnl > 0 ? 'pnl-pos' : data.pnl < 0 ? 'pnl-neg' : ''}>
              {fmtPnl(data.pnl)}
            </strong>
          </span>
          <SplitLine split={pnlSplit(data.by_owner, fmtPnl)} />
          <span>{data.trade_count} trades</span>
          <button type="button" className="reports-month-close-btn" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
      <div className="reports-month-detail-grid">
        <div className="reports-month-detail-dow">
          {DOW_LABELS.map(l => (
            <span key={l}>{l}</span>
          ))}
          <span>Total</span>
        </div>
        {data.weeks.map(week => (
          <div key={week.week_index} className="reports-month-detail-row">
            {week.days.map(iso => {
              const { year, month, day } = parseIso(iso);
              const inMonth = year === data.year && month === data.month;
              const cell = byDate.get(iso) ?? null;
              const result = cell?.result;
              const cls = [
                'reports-day-cell',
                inMonth ? '' : 'reports-day-outside',
                result === 'win' ? 'reports-day-win' : '',
                result === 'loss' ? 'reports-day-loss' : '',
              ]
                .filter(Boolean)
                .join(' ');
              return (
                <div key={iso} className={cls}>
                  <span className="reports-day-num">{day}</span>
                  <span className="reports-day-pnl">{fmtPnlShort(cell?.pnl ?? 0)}</span>
                  <span className="reports-day-trades">{cell?.trade_count ?? 0} trades</span>
                  {cell && cell.trade_count > 0 && (
                    <SplitLine split={pnlSplit(cell.by_owner, fmtPnlShort)} books={tradedBooks(cell.by_owner)} />
                  )}
                </div>
              );
            })}
            <div className="reports-week-total">
              <span className="reports-day-pnl">{fmtPnlShort(week.pnl)}</span>
              <span className="reports-day-trades">{week.trade_count} trades</span>
              {week.trade_count > 0 && <SplitLine split={pnlSplit(week.by_owner, fmtPnlShort)} />}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
