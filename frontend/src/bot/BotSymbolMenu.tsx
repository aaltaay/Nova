import { useEffect, useState, useSyncExternalStore } from 'react';
import { BOT_ALLOWLIST_ADD, BOT_ALLOWLIST_REMOVE } from '../constantGroups/bot';
import {
  closeBotSymbolMenu,
  subscribeBotSymbolMenu,
  type BotSymbolMenuOpen,
} from './botSymbolMenuStore';
import { useBotAllowlist } from './useBotAllowlist';
import {
  getRecordingSymbols,
  getSessionRecordError,
  isTabRecording,
  startTabRecord,
  stopTabRecord,
  subscribeSessionRecord,
} from '../capture/sessionRecordStore';
import { HoldToStopButton } from '../capture/HoldToStopButton';
import { captureStopHoldLabel } from '../capture/constants';

export function BotSymbolMenuHost() {
  const [open, setOpen] = useState<BotSymbolMenuOpen>(null);
  const [recordError, setRecordError] = useState<string | null>(null);
  const [recordBusy, setRecordBusy] = useState(false);
  const { isAllowed, add, remove } = useBotAllowlist();
  const recordEpoch = useSyncExternalStore(
    subscribeSessionRecord,
    () => `${getRecordingSymbols().join(',')}|${getSessionRecordError() || ''}`,
    () => '',
  );

  useEffect(() => subscribeBotSymbolMenu(value => {
    setRecordError(null);
    setOpen(value);
  }), []);

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
  const recording = isTabRecording(open.symbol);
  void recordEpoch;
  const toggle = async (stop: boolean) => {
    setRecordBusy(true);
    setRecordError(null);
    const err = stop ? await stopTabRecord(open.symbol) : await startTabRecord(open.symbol);
    setRecordBusy(false);
    if (err) {
      setRecordError(err);
      return;
    }
    closeBotSymbolMenu();
  };

  return (
    <div
      className="bot-symbol-menu"
      role="menu"
      data-testid="bot-symbol-menu"
      style={{ top: open.y, left: open.x }}
    >
      {recording ? (
        // A recording is locked: Stop takes a deliberate hold, never a slip.
        <HoldToStopButton
          testId="bot-symbol-menu-record"
          label={captureStopHoldLabel(open.symbol)}
          disabled={recordBusy}
          onConfirm={() => void toggle(true)}
        />
      ) : (
        <button
          type="button"
          role="menuitem"
          data-testid="bot-symbol-menu-record"
          disabled={recordBusy}
          onClick={() => void toggle(false)}
        >
          Record -- {open.symbol}
        </button>
      )}
      {(recordError || getSessionRecordError()) && (
        <div role="alert">{recordError || getSessionRecordError()}</div>
      )}
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
