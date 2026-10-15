/** Symbol button for a table row: click selects the row's symbol and opens Trader (ADR 011), through the desk's one
 * ticker link (workspace/TickerLink). Double-click has no special action. Optional listing exchange renders
 * under the ticker (same secondary stack style as dollar change under %). */
import { TickerLink } from './TickerLink';

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
      <TickerLink
        symbol={symbol}
        className={`${selected ? 'active' : ''}${className ? ` ${className}` : ''}`.trim()}
        onOpen={() => {
          onSelect(symbol);
          onOpenTrading(symbol);
        }}
      >
        {symbol}
      </TickerLink>
      {exchange ? (
        <span className="cell-stack-secondary" title={`Listed on ${exchange}`}>
          {exchange}
        </span>
      ) : null}
    </span>
  );
}
