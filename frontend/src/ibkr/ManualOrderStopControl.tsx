import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { Check, ChevronDown } from 'lucide-react';
import {
  TICKER_TRADE_HINT_STOP,
  TICKER_TRADE_HINT_STOP_LIMIT,
  TICKER_TRADE_HINT_TRAILING_STOP,
  TICKER_TRADE_LABEL_STOP,
  TICKER_TRADE_LABEL_STOP_LIMIT,
  TICKER_TRADE_LABEL_STOP_TYPES,
  TICKER_TRADE_LABEL_TRAILING_STOP,
  TICKER_TRADE_LABEL_TRAIL_STOP_SHORT,
} from '../constants';
import { isStopFamilyType, type ManualOrderType } from './orderEntry';
import type { BindOrderExplainer } from './useOrderExplainer';

interface Props {
  orderType: ManualOrderType;
  disabled: boolean;
  /** Why `disabled` is set -- each locked button says it (ux/whyTip.ts). */
  why?: string | null;
  onOrderTypeChange: (orderType: ManualOrderType) => void;
  /** The ticket's hover card: what each stop type does (useOrderExplainer.tsx). */
  explain?: BindOrderExplainer;
}

interface StopType {
  value: ManualOrderType;
  label: string;
  /** What the split button reads while this type is chosen. */
  face: string;
  hint: string;
  testId: string;
}

const STOP_TYPES: readonly StopType[] = [
  {
    value: 'STP',
    label: TICKER_TRADE_LABEL_STOP,
    face: TICKER_TRADE_LABEL_STOP,
    hint: TICKER_TRADE_HINT_STOP,
    testId: 'manual-order-stop-menu-stop',
  },
  {
    value: 'STP LMT',
    label: TICKER_TRADE_LABEL_STOP_LIMIT,
    face: TICKER_TRADE_LABEL_STOP_LIMIT,
    hint: TICKER_TRADE_HINT_STOP_LIMIT,
    testId: 'manual-order-type-stop-limit',
  },
  {
    value: 'TRAIL',
    label: TICKER_TRADE_LABEL_TRAILING_STOP,
    face: TICKER_TRADE_LABEL_TRAIL_STOP_SHORT,
    hint: TICKER_TRADE_HINT_TRAILING_STOP,
    testId: 'manual-order-type-trail',
  },
];

function menuItems(menu: HTMLElement | null): HTMLButtonElement[] {
  return Array.from(menu?.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]') ?? []);
}

/**
 * The order-type row's Stop cell: a split button whose face is the stop type
 * in use (plain Stop until another is chosen) and a caret that opens the
 * Stop types menu -- one panel listing all three, the chosen one checked.
 */
export function ManualOrderStopControl({
  orderType,
  disabled,
  why = null,
  onOrderTypeChange,
  explain,
}: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const caretRef = useRef<HTMLButtonElement>(null);
  const familyActive = isStopFamilyType(orderType);
  const current = STOP_TYPES.find(item => item.value === orderType);
  const face = familyActive && current ? current : STOP_TYPES[0];
  const lockWhy = disabled ? why || undefined : undefined;
  // A ticket that locks while the menu is open closes it.
  const menuOpen = open && !disabled;

  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (event: MouseEvent) => {
      if (rootRef.current?.contains(event.target as Node)) return;
      setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    // Open on the chosen type, so Enter keeps it and the arrows move from it.
    const items = menuItems(menuRef.current);
    const checked = items.find(item => item.getAttribute('aria-checked') === 'true');
    (checked ?? items[0])?.focus();
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [menuOpen]);

  function pick(next: ManualOrderType) {
    onOrderTypeChange(next);
    setOpen(false);
  }

  function onMenuKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      event.preventDefault();
      setOpen(false);
      caretRef.current?.focus();
      return;
    }
    if (event.key === 'Tab') {
      setOpen(false);
      return;
    }
    const items = menuItems(menuRef.current);
    const at = items.indexOf(event.currentTarget.ownerDocument.activeElement as HTMLButtonElement);
    let next = -1;
    if (event.key === 'ArrowDown') next = (at + 1) % items.length;
    else if (event.key === 'ArrowUp') next = (at - 1 + items.length) % items.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = items.length - 1;
    if (next < 0) return;
    event.preventDefault();
    items[next]?.focus();
  }

  return (
    <div className="manual-order-stop-wrap" ref={rootRef}>
      <div className={`manual-order-stop-split${familyActive ? ' is-active' : ''}`}>
        <button
          type="button"
          className={`manual-order-stop-face${familyActive ? ' is-active' : ''}`}
          aria-pressed={familyActive}
          {...explain?.(face.value)}
          onClick={() => pick(face.value)}
          disabled={disabled}
          data-why={lockWhy}
          data-testid="manual-order-type-stop"
        >
          {face.face}
        </button>
        <button
          ref={caretRef}
          type="button"
          className={`manual-order-stop-caret${menuOpen ? ' is-open' : ''}`}
          aria-label={TICKER_TRADE_LABEL_STOP_TYPES}
          aria-expanded={menuOpen}
          aria-haspopup="menu"
          title={lockWhy ? undefined : TICKER_TRADE_LABEL_STOP_TYPES}
          onClick={event => {
            event.stopPropagation();
            setOpen(value => !value);
          }}
          onKeyDown={event => {
            if (event.key !== 'ArrowDown' || menuOpen) return;
            event.preventDefault();
            setOpen(true);
          }}
          disabled={disabled}
          data-why={lockWhy}
          data-testid="manual-order-stop-caret"
        >
          <ChevronDown size={13} strokeWidth={2.4} aria-hidden="true" />
        </button>
      </div>
      {menuOpen ? (
        <div
          ref={menuRef}
          className="manual-order-stop-menu"
          role="menu"
          aria-label={TICKER_TRADE_LABEL_STOP_TYPES}
          onKeyDown={onMenuKeyDown}
          data-testid="manual-order-stop-flyout"
        >
          {STOP_TYPES.map(item => {
            const checked = orderType === item.value;
            return (
              <button
                key={item.value}
                type="button"
                role="menuitemradio"
                aria-checked={checked}
                className="manual-order-stop-menu__item"
                {...explain?.(item.value)}
                onClick={() => pick(item.value)}
                disabled={disabled}
                data-why={lockWhy}
                data-testid={item.testId}
              >
                <span className="manual-order-stop-menu__check" aria-hidden="true">
                  {checked ? <Check size={13} strokeWidth={2.6} /> : null}
                </span>
                <span className="manual-order-stop-menu__text">
                  <span className="manual-order-stop-menu__label">{item.label}</span>
                  <span className="manual-order-stop-menu__hint">{item.hint}</span>
                </span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
