/**
 * Watch eye + REC dot beside the ticker (approved UX redesign).
 * Eye = on the operator's watch list; REC = the symbol is recording.
 * Nothing is drawn for a symbol with neither fact. The bot dot is gone: the
 * strategies only watch and never trade (ADR 072).
 */
import { SCANNER_MARK_REC_TITLE } from '../constantGroups/scanner_board';
import { useIsWatched, WatchMark } from '../watch_list';
import { useScannerRowFacts } from './useScannerRowFacts';

export function ScannerRowMarks({ symbol }: { symbol: string }) {
  const { recording } = useScannerRowFacts(symbol);
  const watched = useIsWatched(symbol);
  if (!recording && !watched) return null;
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
    </span>
  );
}
