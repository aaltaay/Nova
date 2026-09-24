/**
 * Watch eye + REC dot + bot dot beside the ticker (approved UX redesign).
 * Eye = on the operator's watch list. Filled bot dot = allowlisted with a
 * held depth line known to this window; hollow = allowlisted and quiet.
 * Nothing is drawn for a symbol with none of these facts.
 */
import {
  SCANNER_MARK_BOT_HELD_TITLE,
  SCANNER_MARK_BOT_QUIET_TITLE,
  SCANNER_MARK_REC_TITLE,
} from '../constantGroups/scanner_board';
import { useIsWatched, WatchMark } from '../watch_list';
import { useScannerRowFacts } from './useScannerRowFacts';

export function ScannerRowMarks({ symbol }: { symbol: string }) {
  const { recording, allowlisted, depthHeld } = useScannerRowFacts(symbol);
  const watched = useIsWatched(symbol);
  if (!recording && !allowlisted && !watched) return null;
  return (
    <span className="scanner-row-marks" data-testid="scanner-row-marks">
      <WatchMark symbol={symbol} />
      {recording ? (
        <i
          className="scanner-mark scanner-mark--rec"
          title={SCANNER_MARK_REC_TITLE(symbol)}
          data-testid="scanner-mark-rec"
        />
      ) : null}
      {allowlisted ? (
        <i
          className={`scanner-mark scanner-mark--bot${depthHeld ? '' : ' is-quiet'}`}
          title={depthHeld ? SCANNER_MARK_BOT_HELD_TITLE(symbol) : SCANNER_MARK_BOT_QUIET_TITLE(symbol)}
          data-testid="scanner-mark-bot"
          data-held={depthHeld ? '1' : '0'}
        />
      ) : null}
    </span>
  );
}
