/** Table body row: click anywhere → side panel; double-click → full trading view. */
import type { ReactNode, KeyboardEvent } from 'react';

interface Props {
  symbol: string;
  selected: boolean;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  children: ReactNode;
  className?: string;
}

export function SelectableTableRow({
  symbol,
  selected,
  onSelect,
  onOpenTrading,
  children,
  className = '',
}: Props) {
  function onKeyDown(e: KeyboardEvent<HTMLTableRowElement>) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onSelect(symbol);
    }
  }

  return (
    <tr
      className={`selectable-row${selected ? ' row-selected' : ''}${className ? ` ${className}` : ''}`}
      onClick={() => onSelect(symbol)}
      onDoubleClick={() => onOpenTrading(symbol)}
      onKeyDown={onKeyDown}
      tabIndex={0}
      aria-selected={selected}
      title="Click: load side panel · Double-click: open full trading view"
    >
      {children}
    </tr>
  );
}
