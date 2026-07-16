/** Table body row: click anywhere → Quote Panel; double-click → Stock View. */
import { useEffect, useRef, type CSSProperties, type ReactNode, type KeyboardEvent } from 'react';
import { SYMBOL_DOUBLE_CLICK_MS } from '../constants';
import { createClickVsDoubleClick } from '../utils/clickVsDoubleClick';

interface Props {
  symbol: string;
  selected: boolean;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}

export function SelectableTableRow({
  symbol,
  selected,
  onSelect,
  onOpenTrading,
  children,
  className = '',
  style,
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
    return () => handlersRef.current.cancel();
  }, []);

  function onKeyDown(e: KeyboardEvent<HTMLTableRowElement>) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onSelect(symbol);
    }
  }

  return (
    <tr
      className={`selectable-row${selected ? ' row-selected' : ''}${className ? ` ${className}` : ''}`}
      style={style}
      onClick={() => handlersRef.current.handleClick()}
      onKeyDown={onKeyDown}
      tabIndex={0}
      aria-selected={selected}
      title="Click: Quote Panel · Double-click: Stock View (new window)"
    >
      {children}
    </tr>
  );
}
