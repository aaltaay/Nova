/** Symbol button: click → Quote Panel; double-click → Stock View (new tab).
 * Optional listing exchange renders under the ticker (same secondary stack
 * style as dollar change under %). */
import { QUOTE_PANEL_TITLE, STOCK_VIEW_TITLE } from '../constants';

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
        }}
        onDoubleClick={e => {
          e.preventDefault();
          e.stopPropagation();
          onOpenTrading(symbol);
        }}
        title={`Click: ${QUOTE_PANEL_TITLE} · Double-click: ${STOCK_VIEW_TITLE} (new tab)`}
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
