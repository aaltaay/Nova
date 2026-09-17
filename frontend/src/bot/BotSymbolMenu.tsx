import { useEffect, useState } from 'react';
import { BOT_ALLOWLIST_ADD, BOT_ALLOWLIST_REMOVE } from '../constantGroups/bot';
import {
  closeBotSymbolMenu,
  subscribeBotSymbolMenu,
  type BotSymbolMenuOpen,
} from './botSymbolMenuStore';
import { useBotAllowlist } from './useBotAllowlist';

export function BotSymbolMenuHost() {
  const [open, setOpen] = useState<BotSymbolMenuOpen>(null);
  const { isAllowed, add, remove } = useBotAllowlist();

  useEffect(() => subscribeBotSymbolMenu(setOpen), []);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeBotSymbolMenu();
    };
    const onDown = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest('[data-testid="bot-symbol-menu"]')) return;
      closeBotSymbolMenu();
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mousedown', onDown);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mousedown', onDown);
    };
  }, [open]);

  if (!open) return null;
  const allowed = isAllowed(open.symbol);
  return (
    <div
      className="bot-symbol-menu"
      role="menu"
      data-testid="bot-symbol-menu"
      style={{ top: open.y, left: open.x }}
    >
      <button
        type="button"
        role="menuitem"
        data-testid="bot-symbol-menu-toggle"
        onClick={() => {
          void (allowed ? remove(open.symbol) : add(open.symbol));
          closeBotSymbolMenu();
        }}
      >
        {allowed ? BOT_ALLOWLIST_REMOVE : BOT_ALLOWLIST_ADD} -- {open.symbol}
      </button>
    </div>
  );
}
