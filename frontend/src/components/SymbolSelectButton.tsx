/** Symbol button: click opens Trader and replaces the active tab (ADR 011).
 * Double-click has no special action. Optional listing exchange renders
 * under the ticker (same secondary stack style as dollar change under %). */
import { TICKER_OPEN_TRADER_TITLE } from '../constants';

interface Props {
  symbol: string;
  exchange?: string | null;
  selected?: boolean;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  className?: string;
}

export function SymbolSelectButton({
  symbol,
  exchange,
  selected = false,
  onSelect,
  onOpenTrading,
  className = '',
}: Props) {
  return (
    <span className="cell-stack symbol-cell">
      <button
        type="button"
        className={`symbol-btn${selected ? ' active' : ''}${className ? ` ${className}` : ''}`}
        onClick={e => {
          e.stopPropagation();
          onSelect(symbol);
          onOpenTrading(symbol);
        }}
        title={TICKER_OPEN_TRADER_TITLE}
      >
        {symbol}
      </button>
      {exchange ? (
        <span className="cell-stack-secondary" title={`Listed on ${exchange}`}>
          {exchange}
        </span>
      ) : null}
    </span>
  );
}
