/** Earnings tab -- Finnhub calendar, day bands + BEFORE OPEN / AFTER CLOSE
 * lanes (1c layout). Not an IBKR scanner lease and not a HOD Momo input
 * (single-market-data-feed.mdc) -- a metadata list, same class as Catalysts.
 * Ticker click opens Trader the same way every other scanner ticker does. */
import { useState } from 'react';
import { EARNINGS_RANGES, EARNINGS_RANGE_LABELS } from '../constants';
import { useEarningsCalendar } from './useEarningsCalendar';
import { earningsErrorCopy } from './earningsError';
import { EarningsDayBand } from './EarningsDayBand';
import type { EarningsRange } from '../types/earnings';

export function EarningsPanel({
  selectedSymbol,
  onSelect,
  onOpenTrading,
}: {
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}) {
  const [range, setRange] = useState<EarningsRange>('today');
  const { view, loading, fetchError } = useEarningsCalendar(range);

  const totalReports = view?.days.reduce((sum, d) => sum + d.count, 0) ?? 0;
  const hasDays = Boolean(view?.days.length);
  const error = earningsErrorCopy(view?.error || fetchError || null, hasDays);

  return (
    <div className="earnings-panel">
      <div className="earnings-panel__header">
        <div className="earnings-panel__ranges">
          {EARNINGS_RANGES.map((r) => (
            <button
              key={r}
              type="button"
              className={`earnings-panel__range${range === r ? ' active' : ''}`}
              onClick={() => setRange(r)}
            >
              {EARNINGS_RANGE_LABELS[r]}
            </button>
          ))}
        </div>
        <span className="earnings-panel__count">
          {loading && !view ? 'Loading…' : `${totalReports} reports`}
        </span>
      </div>

      {error ? <div className="empty-state">{error}</div> : null}
      {hasDays ? (
        <div className="earnings-panel__days">
          {view!.days.map((day) => (
            <EarningsDayBand
              key={day.date}
              day={day}
              selectedSymbol={selectedSymbol}
              onSelect={onSelect}
              onOpenTrading={onOpenTrading}
            />
          ))}
        </div>
      ) : error ? null : view ? (
        <div className="empty-state">No earnings reports in this range.</div>
      ) : (
        <div className="empty-state">Loading earnings calendar…</div>
      )}
    </div>
  );
}
