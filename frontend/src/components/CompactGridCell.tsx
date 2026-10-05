/** Label/value cell used by ticker quote and fundamentals grids. */
import { memo, type ReactNode } from 'react';

/** Memoized: the quote stats render on every print, and most of their cells did not change (#707). */
export const CompactGridCell = memo(function CompactGridCell({
  label,
  value,
  valueClass,
  title,
}: {
  label: string;
  value: ReactNode;
  valueClass?: string;
  /** Tooltip on the whole cell (e.g. data-source attribution). */
  title?: string;
}) {
  return (
    <div className="cq-cell" title={title}>
      <span className="cq-label">{label}</span>
      <span className={`cq-value${valueClass ? ' ' + valueClass : ''}`}>{value}</span>
    </div>
  );
});
