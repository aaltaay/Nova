/** Symbol button: click → Quote Panel; double-click → Stock View (new window).
 * Optional listing exchange renders under the ticker (same secondary stack
 * style as dollar change under %). */
import { useEffect, useRef } from 'react';
import {
  QUOTE_PANEL_TITLE,
  STOCK_VIEW_TITLE,
  SYMBOL_DOUBLE_CLICK_MS,
} from '../constants';
import { createClickVsDoubleClick } from '../utils/clickVsDoubleClick';

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
  const symbolRef = useRef(symbol);
  const onSelectRef = useRef(onSelect);
  const onOpenRef = useRef(onOpenTrading);
  symbolRef.current = symbol;
  onSelectRef.current = onSelect;
  onOpenRef.current = onOpenTrading;

  const handlersRef = useRef(
    createClickVsDoubleClick(
      () => onSelectRef.current(symbolRef.current),
      () => onOpenRef.current(symbolRef.current),
      SYMBOL_DOUBLE_CLICK_MS,
    ),
  );

  useEffect(() => {
    const handlers = handlersRef.current;
    return () => handlers.cancel();
  }, []);

  return (
    <span className="cell-stack symbol-cell">
      <button
        type="button"
        className={`symbol-btn${selected ? ' active' : ''}${className ? ` ${className}` : ''}`}
        onClick={e => {
          e.stopPropagation();
          handlersRef.current.handleClick();
        }}
        title={`Click: ${QUOTE_PANEL_TITLE} · Double-click: ${STOCK_VIEW_TITLE} (new window)`}
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
