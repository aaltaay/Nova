/**
 * Hover actions at the right end of a scanner row: Trader, Record / Stop rec
 * (hold), Allowlist / Allowlisted, Pin. State-aware labels so a button never
 * lies about what it will do. Clicks never reach the row (which would
 * re-select).
 */
import { useState, type MouseEvent, type KeyboardEvent } from 'react';
import { useBotAllowlist } from '../bot/useBotAllowlist';
import { HoldToStopButton } from '../capture/HoldToStopButton';
import { startTabRecord, stopTabRecord } from '../capture/sessionRecordStore';
import {
  SCANNER_ACTION_ALLOWLIST,
  SCANNER_ACTION_ALLOWLISTED,
  SCANNER_ACTION_ALLOWLISTED_TITLE,
  SCANNER_ACTION_PIN,
  SCANNER_ACTION_PIN_TITLE,
  SCANNER_ACTION_RECORD,
  SCANNER_ACTION_STOP_REC,
  SCANNER_ACTION_TRADER,
  SCANNER_ACTION_TRADER_TITLE,
  SCANNER_ACTION_UNPIN,
  SCANNER_ACTION_UNPIN_TITLE,
} from '../constantGroups/scanner_board';
import { BOT_ALLOWLIST_ADD } from '../constantGroups/bot';
import { togglePinnedRow, usePinnedRow } from '../scanner/pinnedRowsStore';
import { useScannerRowFacts } from './useScannerRowFacts';

type Props = {
  symbol: string;
  onOpenTrading: (symbol: string) => void;
};

const swallow = (e: MouseEvent | KeyboardEvent) => e.stopPropagation();

export function ScannerRowActions({ symbol, onOpenTrading }: Props) {
  const { recording, allowlisted } = useScannerRowFacts(symbol);
  const { add, remove } = useBotAllowlist();
  const pinned = usePinnedRow(symbol);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleRecord = async (stop: boolean) => {
    setBusy(true);
    setError(null);
    const err = stop ? await stopTabRecord(symbol) : await startTabRecord(symbol);
    setBusy(false);
    if (err) setError(err);
  };

  return (
    <span
      className="scanner-row-actions"
      data-testid="scanner-row-actions"
      onClick={swallow}
      onDoubleClick={swallow}
      onKeyDown={swallow}
      onContextMenu={swallow}
    >
      <button
        type="button"
        className="scanner-row-actions__btn is-primary"
        title={SCANNER_ACTION_TRADER_TITLE}
        data-testid="scanner-row-trader"
        onClick={() => onOpenTrading(symbol)}
      >
        {SCANNER_ACTION_TRADER}
      </button>
      {recording ? (
        <HoldToStopButton
          label={SCANNER_ACTION_STOP_REC}
          disabled={busy}
          onConfirm={() => void toggleRecord(true)}
          testId="scanner-row-stop-rec"
        />
      ) : (
        <button
          type="button"
          className="scanner-row-actions__btn"
          data-testid="scanner-row-record"
          disabled={busy}
          onClick={() => void toggleRecord(false)}
        >
          <i className="scanner-mark scanner-mark--rec" aria-hidden="true" />
          {SCANNER_ACTION_RECORD}
        </button>
      )}
      <button
        type="button"
        className={`scanner-row-actions__btn${allowlisted ? ' is-state' : ''}`}
        title={allowlisted ? SCANNER_ACTION_ALLOWLISTED_TITLE : BOT_ALLOWLIST_ADD}
        aria-pressed={allowlisted}
        data-testid="scanner-row-allowlist"
        onClick={() => void (allowlisted ? remove(symbol) : add(symbol))}
      >
        {allowlisted ? SCANNER_ACTION_ALLOWLISTED : SCANNER_ACTION_ALLOWLIST}
      </button>
      <button
        type="button"
        className={`scanner-row-actions__btn${pinned ? ' is-state' : ''}`}
        title={pinned ? SCANNER_ACTION_UNPIN_TITLE : SCANNER_ACTION_PIN_TITLE}
        aria-pressed={pinned}
        data-testid="scanner-row-pin"
        onClick={() => togglePinnedRow(symbol)}
      >
        {pinned ? SCANNER_ACTION_UNPIN : SCANNER_ACTION_PIN}
      </button>
      {error ? <span role="alert" className="scanner-row-actions__error">{error}</span> : null}
    </span>
  );
}
