/**
 * One nav-rail row: icon + label (+ optional trailing count / badge).
 * Active rows carry the accent bar via `.is-active` (navRail.css).
 */
import type { ReactNode } from 'react';

export interface NavRailItemProps {
  testId: string;
  icon: ReactNode;
  label: string;
  title: string;
  active: boolean;
  onClick: () => void;
  className?: string;
  /** Right-aligned count text; omitted when empty. */
  count?: string;
  /** Trailing node (recording badge dot). */
  trailing?: ReactNode;
  /** Rail-child ids for the module-registry e2e (`[data-tab=...]`). */
  dataTab?: string;
  ariaExpanded?: boolean;
  ariaControls?: string;
}

export function NavRailItem({
  testId,
  icon,
  label,
  title,
  active,
  onClick,
  className,
  count,
  trailing,
  dataTab,
  ariaExpanded,
  ariaControls,
}: NavRailItemProps) {
  return (
    <button
      type="button"
      className={`nav-rail__item${className ? ` ${className}` : ''}${active ? ' is-active' : ''}`}
      data-testid={testId}
      data-tab={dataTab}
      title={title}
      aria-current={active ? 'page' : undefined}
      aria-expanded={ariaExpanded}
      aria-controls={ariaControls}
      onClick={onClick}
    >
      {icon}
      <span className="nav-rail__txt">{label}</span>
      {count ? <em className="nav-rail__count">{count}</em> : null}
      {trailing}
    </button>
  );
}
