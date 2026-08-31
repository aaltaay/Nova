/** Sticky date header + BEFORE OPEN / AFTER CLOSE lanes for one calendar day
 * (1c layout). Intraday (Finnhub `dmh` / unknown hour) renders as a third,
 * clearly-labeled strip below so no name is silently dropped. */
import { EARNINGS_SESSION_LABELS } from '../constants';
import { EarningsLane } from './EarningsLane';
import type { EarningsDay } from '../types/earnings';

export function EarningsDayBand({
  day,
  selectedSymbol,
  onSelect,
  onOpenTrading,
}: {
  day: EarningsDay;
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}) {
  return (
    <div className="earnings-day-band">
      <div className="earnings-day-band__header">
        <span className="earnings-day-band__date">{day.label}</span>
        <span className="earnings-day-band__count">{day.count} reports</span>
      </div>
      <div className="earnings-day-band__lanes">
        <EarningsLane
          label={EARNINGS_SESSION_LABELS.bmo}
          rows={day.bmo}
          selectedSymbol={selectedSymbol}
          onSelect={onSelect}
          onOpenTrading={onOpenTrading}
        />
        <EarningsLane
          label={EARNINGS_SESSION_LABELS.amc}
          rows={day.amc}
          selectedSymbol={selectedSymbol}
          onSelect={onSelect}
          onOpenTrading={onOpenTrading}
        />
      </div>
      <EarningsLane
        label={EARNINGS_SESSION_LABELS.intraday}
        rows={day.intraday}
        selectedSymbol={selectedSymbol}
        onSelect={onSelect}
        onOpenTrading={onOpenTrading}
      />
    </div>
  );
}
