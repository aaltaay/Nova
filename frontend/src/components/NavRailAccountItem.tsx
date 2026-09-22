/**
 * Account row of the nav rail. Click opens the Account page; hover or focus
 * drops the Fund account popover beside it (IBKR Client Portal) -- the same
 * door the retired header icon held, reachable whether or not Gateway is up.
 * The popover is position:fixed so the rail's overflow never clips it.
 */
import { useEffect, useId, useRef, useState } from 'react';
import { GLOBAL_BAR_ACCOUNT_MENU_LABEL } from '../constants';
import {
  NAV_RAIL_LABEL_ACCOUNT,
  NAV_RAIL_TITLE_ACCOUNT,
} from '../constantGroups/nav_rail';
import { FundAccountButton } from '../ibkr/FundAccountButton';
import { navRailIcon } from './navRailIcons';
import { NavRailItem } from './NavRailItem';

interface Props {
  active: boolean;
  onOpen: () => void;
}

export function NavRailAccountItem({ active, onOpen }: Props) {
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState<{ top: number; left: number } | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  const show = () => {
    const rect = wrapRef.current?.getBoundingClientRect();
    if (rect) setAnchor({ top: rect.top, left: rect.right });
    setOpen(true);
  };

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
      className="nav-rail__account"
      ref={wrapRef}
      data-testid="nav-rail-account-menu-wrap"
      onMouseEnter={show}
      onMouseLeave={() => setOpen(false)}
      onFocus={show}
      onBlur={(e) => {
        if (!wrapRef.current?.contains(e.relatedTarget as Node | null)) setOpen(false);
      }}
    >
      <NavRailItem
        testId="nav-rail-account"
        icon={navRailIcon('account')}
        label={NAV_RAIL_LABEL_ACCOUNT}
        title={NAV_RAIL_TITLE_ACCOUNT}
        active={active}
        ariaControls={open ? menuId : undefined}
        onClick={() => {
          setOpen(false);
          onOpen();
        }}
      />
      {open && (
        <div
          id={menuId}
          className="nav-rail__account-menu"
          style={anchor ? { top: anchor.top, left: anchor.left } : undefined}
          role="group"
          aria-label={GLOBAL_BAR_ACCOUNT_MENU_LABEL}
          data-testid="nav-rail-account-menu"
        >
          <FundAccountButton />
        </div>
      )}
    </div>
  );
}
