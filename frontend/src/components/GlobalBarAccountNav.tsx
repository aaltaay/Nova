/**
 * Account icon for GlobalAppBar. Click opens the trading tab; hover or focus
 * drops a small popover under it that holds Fund account (IBKR Client Portal).
 * Fund stays reachable whether or not Gateway is connected.
 */
import { useEffect, useId, useRef, useState } from 'react';
import {
  GLOBAL_BAR_ACCOUNT_LABEL,
  GLOBAL_BAR_ACCOUNT_MENU_LABEL,
  GLOBAL_BAR_ACCOUNT_TITLE,
} from '../constants';
import { FundAccountButton } from '../ibkr/FundAccountButton';

interface Props {
  active: boolean;
  onOpenAccount: () => void;
}

export function GlobalBarAccountNav({ active, onOpenAccount }: Props) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div
      className="global-app-bar__account-nav-wrap"
      ref={wrapRef}
      data-testid="global-bar-account-menu-wrap"
      onMouseEnter={() => setOpen(true)}
      onFocus={() => setOpen(true)}
      onBlur={e => {
        if (!wrapRef.current?.contains(e.relatedTarget as Node | null)) setOpen(false);
      }}
    >
      <button
        type="button"
        className={`global-app-bar__account-nav global-app-bar__icon-btn${active ? ' is-active' : ''}`}
        title={GLOBAL_BAR_ACCOUNT_TITLE}
        aria-label={GLOBAL_BAR_ACCOUNT_LABEL}
        aria-pressed={active}
        aria-controls={open ? menuId : undefined}
        data-testid="global-bar-account-nav"
        onClick={() => {
          setOpen(false);
          onOpenAccount();
        }}
      >
        <span aria-hidden="true">👤</span>
      </button>
      {open && (
        <div
          id={menuId}
          className="global-app-bar__card global-app-bar__account-menu"
          role="group"
          aria-label={GLOBAL_BAR_ACCOUNT_MENU_LABEL}
          data-testid="global-bar-account-menu"
        >
          <FundAccountButton />
        </div>
      )}
    </div>
  );
}
