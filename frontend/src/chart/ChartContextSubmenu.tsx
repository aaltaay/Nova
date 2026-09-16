/**
 * Shared flyout for Drawings / Show Layers. Positioned by chartSubmenuPosition.
 */
import type { ReactNode, Ref } from 'react';

export function ChartContextSubmenu(props: {
  testId: string;
  ariaLabel: string;
  top: number;
  left: number;
  children: ReactNode;
}) {
  return (
    <div
      className="chart-context-menu chart-context-menu--submenu"
      role="menu"
      aria-label={props.ariaLabel}
      data-testid={props.testId}
      style={{ top: props.top, left: props.left }}
    >
      {props.children}
    </div>
  );
}

export function ChartContextSubmenuRow(props: {
  testId: string;
  label: string;
  expanded: boolean;
  rowRef: Ref<HTMLButtonElement>;
  onOpen: () => void;
  onToggle: () => void;
}) {
  return (
    <button
      ref={props.rowRef}
      type="button"
      role="menuitem"
      className="chart-context-menu__item chart-context-menu__item--submenu"
      aria-haspopup="menu"
      aria-expanded={props.expanded}
      data-testid={props.testId}
      onPointerEnter={props.onOpen}
      onClick={props.onToggle}
    >
      <span>{props.label}</span>
      <span aria-hidden="true" className="chart-context-menu__caret">›</span>
    </button>
  );
}
