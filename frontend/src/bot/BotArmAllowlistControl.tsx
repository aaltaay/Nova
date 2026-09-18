import { useEffect, useState } from 'react';
import {
  BOT_ALLOWLIST_STRIP_TITLE,
  botAllowlistStripLabel,
} from '../constantGroups/bot';
import { BotAllowlistEditor } from './BotAllowlistEditor';
import { useBotAllowlist } from './useBotAllowlist';

export function BotArmAllowlistControl() {
  const { symbols, add, remove } = useBotAllowlist();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    const onDown = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest('[data-testid="bot-arm-allowlist"]')) return;
      setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mousedown', onDown);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mousedown', onDown);
    };
  }, [open]);

  return (
    <div className="bot-arm__allowlist" data-testid="bot-arm-allowlist">
      <button
        type="button"
        className="bot-arm__btn"
        data-testid="bot-arm-allowlist-toggle"
        aria-expanded={open}
        aria-controls="bot-arm-allowlist-panel"
        aria-haspopup="dialog"
        aria-label={BOT_ALLOWLIST_STRIP_TITLE}
        onClick={() => setOpen(value => !value)}
      >
        {botAllowlistStripLabel(symbols.length)}
      </button>
      {open ? (
        <div
          id="bot-arm-allowlist-panel"
          className="bot-arm__allowlist-panel"
          data-testid="bot-arm-allowlist-panel"
          role="dialog"
          aria-label={BOT_ALLOWLIST_STRIP_TITLE}
        >
          <h3 className="bot-arm__allowlist-title">{BOT_ALLOWLIST_STRIP_TITLE}</h3>
          <BotAllowlistEditor
            testId="bot-arm-allowlist"
            symbols={symbols}
            add={add}
            remove={remove}
          />
        </div>
      ) : null}
    </div>
  );
}
