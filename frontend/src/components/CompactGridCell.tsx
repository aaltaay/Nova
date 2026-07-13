/** Label/value cell used by ticker quote and fundamentals grids. */
import type { ReactNode } from 'react';

export function CompactGridCell({
  label,
  value,
  valueClass,
}: {
  label: string;
  value: ReactNode;
  valueClass?: string;
}) {
  return (
    <div className="cq-cell">
      <span className="cq-label">{label}</span>
      <span className={`cq-value${valueClass ? ' ' + valueClass : ''}`}>{value}</span>
    </div>
  );
}
