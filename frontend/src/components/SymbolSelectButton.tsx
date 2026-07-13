/** Symbol button: click → side panel; double-click → full trading page.
 * Optional listing exchange renders under the ticker (same secondary stack
 * style as dollar change under %). */
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
        title="Click: load side panel · Double-click: open full trading view"
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
