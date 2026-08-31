/** One earnings-calendar card inside a lane (1c layout).
 *
 * Row-vs-ticker spatial split (ADR 011 §7a): the card body only calls
 * `onSelect` (Quote Panel); the blue ticker button is the sole gesture that
 * opens Trader. This is a card grid, not a `<table>`, so it cannot reuse
 * `SelectableTableRow` (which renders a `<tr>`) -- the click contract is
 * replicated here instead. */
import { ROW_SELECT_QUOTE_TITLE } from '../constants';
import { SymbolSelectButton } from '../components/SymbolSelectButton';
import { fmtMarketCap } from '../utils/quoteFormat';
import type { EarningsRow } from '../types/earnings';

function fmtEps(v: number | null): string {
  return v == null ? '—' : `$${v.toFixed(2)}`;
}

export function EarningsCard({
  row,
  selectedSymbol,
  onSelect,
  onOpenTrading,
}: {
  row: EarningsRow;
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
}) {
  const meta = [row.sector, row.market_cap != null ? fmtMarketCap(row.market_cap) : null]
    .filter(Boolean)
    .join(' · ');
  const selected = selectedSymbol === row.symbol;

  return (
    <div
      className={`earnings-card${selected ? ' earnings-card--selected' : ''}`}
      role="button"
      tabIndex={0}
      title={ROW_SELECT_QUOTE_TITLE}
      onClick={() => onSelect(row.symbol)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(row.symbol);
        }
      }}
    >
      <SymbolSelectButton
        symbol={row.symbol}
        selected={selected}
        onSelect={onSelect}
        onOpenTrading={onOpenTrading}
      />
      <div className="earnings-card__body">
        <div className="earnings-card__name" title={row.company_name || undefined}>
          {row.company_name || '—'}
        </div>
        {meta ? <div className="earnings-card__meta">{meta}</div> : null}
      </div>
      <div className="earnings-card__eps">
        <div className="earnings-card__eps-row">
          <span className="earnings-card__eps-label">EPS est</span>
          <span>{fmtEps(row.eps_estimate)}</span>
        </div>
        {row.eps_actual != null ? (
          <div className="earnings-card__eps-row">
            <span className="earnings-card__eps-label">EPS act</span>
            <span>{fmtEps(row.eps_actual)}</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}
