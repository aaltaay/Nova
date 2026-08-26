/**
 * Trash control that cannot delete on the first click.
 */

import { useEffect, useState } from 'react';
import {
  SHORTCUTS_MENU_DELETE_ARM_MS,
  SHORTCUTS_MENU_DELETE_CONFIRM,
} from '../constants';

function TrashIcon() {
  return (
    <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">
      <path
        fill="currentColor"
        d="M6.2 2h3.6l.4 1H14v1.2H2V3h3.8l.4-1zM3.2 5.2h9.6l-.7 8.3H3.9L3.2 5.2zm2.3 1.3v5.4h1.1V6.5H5.5zm3.3 0v5.4h1.1V6.5H8.8z"
      />
    </svg>
  );
}

export function ConfirmDeleteIconButton({
  label,
  onConfirm,
  onArm,
  className = '',
  testId = 'shortcuts-menu-delete-btn',
}: {
  label: string;
  onConfirm: () => void;
  onArm?: () => void;
  className?: string;
  testId?: string;
}) {
  const [armed, setArmed] = useState(false);

  useEffect(() => {
    if (!armed) return undefined;
    const timer = window.setTimeout(() => setArmed(false), SHORTCUTS_MENU_DELETE_ARM_MS);
    return () => window.clearTimeout(timer);
  }, [armed]);

  return (
    <button
      type="button"
      className={`shortcuts-menu-delete-btn${armed ? ' is-armed' : ''}${
        className ? ` ${className}` : ''
      }`}
      data-testid={testId}
      aria-label={armed ? `Click again to delete ${label}` : `Delete ${label}`}
      title={armed ? 'Click again to confirm delete' : `Delete ${label}`}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!armed) {
          onArm?.();
          setArmed(true);
          return;
        }
        setArmed(false);
        onConfirm();
      }}
    >
      <TrashIcon />
      {armed && <span>{SHORTCUTS_MENU_DELETE_CONFIRM}</span>}
    </button>
  );
}
