/** A sortable column header: click (or Enter / Space) sorts by it, and the
 * arrow says which way. Looks like the Scanner's headers (`.sortable-th`). */
import type { KeyboardEvent, ReactNode, ThHTMLAttributes } from 'react';
import { ariaSortFor, type TableSort } from './tableSort';

interface SortThProps extends Omit<ThHTMLAttributes<HTMLTableCellElement>, 'onClick' | 'children'> {
  /** The column key in the table's sort columns. */
  col: string;
  sort: TableSort | null;
  onSort: (key: string) => void;
  children?: ReactNode;
}

export function SortTh({ col, sort, onSort, className, children, ...rest }: SortThProps) {
  const aria = ariaSortFor(sort, col);
  const active = aria !== 'none';
  const onKeyDown = (e: KeyboardEvent<HTMLTableCellElement>) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    e.preventDefault();
    onSort(col);
  };
  return (
    <th
      {...rest}
      className={className ? `sortable-th ${className}` : 'sortable-th'}
      aria-sort={aria}
      tabIndex={0}
      data-sort-col={col}
      onClick={() => onSort(col)}
      onKeyDown={onKeyDown}
    >
      <span className="th-inner">
        <span className="th-label">{children}</span>
        <span className={`sort-arrow${active ? ' active' : ''}`} aria-hidden="true">
          {aria === 'ascending' ? '↑' : aria === 'descending' ? '↓' : '↕'}
        </span>
      </span>
    </th>
  );
}
