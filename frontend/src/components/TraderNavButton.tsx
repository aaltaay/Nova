/**
 * Scanner | Trader control -- main click opens selected/SPY;
 * chevron picks SPY / QQQ / IWM without burning all three L2 slots.
 */
import { useEffect, useId, useRef, useState } from 'react';
import {
  GLOBAL_BAR_NAV_TRADER,
  GLOBAL_BAR_NAV_TRADER_TITLE,
  TRADER_DEFAULT_SYMBOLS,
  TRADER_DEFAULTS_MENU_TITLE,
  TRADER_DEFAULTS_TOGGLE_LABEL,
} from '../constants';

interface Props {
  traderActive: boolean;
  traderSymbol: string;
  onOpen: (symbol: string) => void;
}

export function TraderNavButton({ traderActive, traderSymbol, onOpen }: Props) {
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
    <div className="global-app-bar__trader-nav" ref={wrapRef}>
      <button
        type="button"
        className={`global-app-bar__nav-btn${traderActive ? ' is-active' : ''}`}
        aria-pressed={traderActive}
        title={GLOBAL_BAR_NAV_TRADER_TITLE}
        data-testid="global-bar-nav-trader"
        onClick={() => {
          if (traderActive) return;
          onOpen(traderSymbol);
        }}
      >
        {GLOBAL_BAR_NAV_TRADER}
      </button>
      <button
        type="button"
        className={`global-app-bar__nav-chevron${open ? ' is-open' : ''}`}
        aria-label={TRADER_DEFAULTS_TOGGLE_LABEL}
        aria-expanded={open}
        aria-controls={menuId}
        title={TRADER_DEFAULTS_MENU_TITLE}
        data-testid="global-bar-nav-trader-defaults"
        onClick={() => setOpen((v) => !v)}
      >
        ▾
      </button>
      {open && (
        <div
          className="global-app-bar__trader-defaults"
          id={menuId}
          role="menu"
          aria-label={TRADER_DEFAULTS_TOGGLE_LABEL}
        >
          {TRADER_DEFAULT_SYMBOLS.map((sym) => (
            <button
              key={sym}
              type="button"
              role="menuitem"
              className="global-app-bar__trader-default"
              data-testid={`trader-default-${sym}`}
              onClick={() => {
                setOpen(false);
                onOpen(sym);
              }}
            >
              {sym}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
