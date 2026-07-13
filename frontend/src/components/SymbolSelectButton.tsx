/** Symbol button: click → side panel; double-click → full trading page. */
interface Props {
  symbol: string;
  selected?: boolean;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  className?: string;
}

export function SymbolSelectButton({
  symbol,
  selected = false,
  onSelect,
  onOpenTrading,
  className = '',
}: Props) {
  return (
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
  );
}
