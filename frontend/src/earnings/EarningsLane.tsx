/** One BEFORE OPEN / AFTER CLOSE / Intraday lane inside a day band (1c layout).
 * Truncates to EARNINGS_LANE_PREVIEW_CAP cards with an in-place "+N" expand --
 * no pagination, matches the wireframe's "+25 after close" affordance. */
import { useState } from 'react';
import { EARNINGS_LANE_PREVIEW_CAP } from '../constants';
import { EarningsCard } from './EarningsCard';
import type { EarningsRow } from '../types/earnings';

export function EarningsLane({
  label,
  rows,
  selectedSymbol,
  onSelect,
  onOpenTrading,
}: {
  label: string;
  rows: EarningsRow[];
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  if (rows.length === 0) return null;

  const visible = expanded ? rows : rows.slice(0, EARNINGS_LANE_PREVIEW_CAP);
  const hidden = rows.length - visible.length;

  return (
    <div className="earnings-lane">
      <div className="earnings-lane__label">
        {label} <span className="earnings-lane__count">{rows.length}</span>
      </div>
      <div className="earnings-lane__cards">
        {visible.map((row) => (
          <EarningsCard
            key={row.symbol}
            row={row}
            selectedSymbol={selectedSymbol}
            onSelect={onSelect}
            onOpenTrading={onOpenTrading}
          />
        ))}
      </div>
      {hidden > 0 ? (
        <button
          type="button"
          className="earnings-lane__more"
          onClick={() => setExpanded(true)}
        >
          +{hidden} more
        </button>
      ) : null}
    </div>
  );
}
