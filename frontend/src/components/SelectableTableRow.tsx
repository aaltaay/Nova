/** Table body row: click anywhere → Quote Panel; double-click → Trader. */
import { useEffect, useRef, type CSSProperties, type ReactNode, type KeyboardEvent } from 'react';
import {
  QUOTE_PANEL_TITLE,
  STOCK_VIEW_TITLE,
  SYMBOL_DOUBLE_CLICK_MS,
} from '../constants';
import { createClickVsDoubleClick } from '../utils/clickVsDoubleClick';

interface Props {
  symbol: string;
  selected: boolean;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  /** Optional row tip prepended before the click/double-click hint. */
  hintPrefix?: string;
  /** Marks extremely recent closed fills/cancels for tests + CSS. */
  dataRecent?: boolean;
}

const ROW_NAV_TITLE =
  `Click: ${QUOTE_PANEL_TITLE} · Double-click: ${STOCK_VIEW_TITLE} (new window)`;

export function SelectableTableRow({
  symbol,
  selected,
  onSelect,
  onOpenTrading,
  children,
  className = '',
  style,
  hintPrefix,
  dataRecent = false,
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

  function onKeyDown(e: KeyboardEvent<HTMLTableRowElement>) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onSelect(symbol);
    }
  }

  const title = hintPrefix ? `${hintPrefix} · ${ROW_NAV_TITLE}` : ROW_NAV_TITLE;

  return (
    <tr
      className={`selectable-row${selected ? ' row-selected' : ''}${className ? ` ${className}` : ''}`}
      style={style}
      onClick={() => handlersRef.current.handleClick()}
      onKeyDown={onKeyDown}
      tabIndex={0}
      aria-selected={selected}
      title={title}
      data-recent={dataRecent ? '1' : undefined}
    >
      {children}
    </tr>
  );
}
