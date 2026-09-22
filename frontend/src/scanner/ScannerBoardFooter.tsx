/**
 * Board footer: `N of M match`, what the chips hid (with Show all), what the
 * exchange filter hid, and the one-line legend for the row dots. Rendered
 * only for scanner-row lists.
 */
import {
  SCANNER_FOOTER_LEGEND_BOT_HELD,
  SCANNER_FOOTER_LEGEND_BOT_QUIET,
  SCANNER_FOOTER_LEGEND_REC,
  SCANNER_FOOTER_SHOW_ALL,
  scannerFooterHiddenByChips,
  scannerFooterHiddenByExchange,
  scannerFooterMatch,
} from '../constantGroups/scanner_board';

type Props = {
  /** Rows on screen after every client-side filter. */
  shown: number;
  /** Rows the feed gave for this list (before the exchange filter). */
  total: number;
  hiddenByChips: number;
  hiddenByExchange: number;
  noun: string;
  onShowAll: () => void;
};

export function ScannerBoardFooter({ shown, total, hiddenByChips, hiddenByExchange, noun, onShowAll }: Props) {
  return (
    <footer className="scanner-board__foot" data-testid="scanner-board-footer">
      <span data-testid="scanner-board-match">{scannerFooterMatch(shown, total, noun)}</span>
      {hiddenByChips > 0 ? (
        <>
          <span className="scanner-board__sep" aria-hidden="true">|</span>
          <span data-testid="scanner-board-hidden-chips">
            {scannerFooterHiddenByChips(hiddenByChips)}
            {' · '}
            <button type="button" className="scanner-board__link" onClick={onShowAll} data-testid="scanner-board-show-all">
              {SCANNER_FOOTER_SHOW_ALL}
            </button>
          </span>
        </>
      ) : null}
      {hiddenByExchange > 0 ? (
        <>
          <span className="scanner-board__sep" aria-hidden="true">|</span>
          <span data-testid="scanner-board-hidden-exchange">{scannerFooterHiddenByExchange(hiddenByExchange)}</span>
        </>
      ) : null}
      <span className="scanner-board__spacer" />
      <span className="scanner-board__legend" aria-label="Row mark legend">
        <span><i className="scanner-mark scanner-mark--rec" aria-hidden="true" />{SCANNER_FOOTER_LEGEND_REC}</span>
        <span><i className="scanner-mark scanner-mark--bot" aria-hidden="true" />{SCANNER_FOOTER_LEGEND_BOT_HELD}</span>
        <span><i className="scanner-mark scanner-mark--bot is-quiet" aria-hidden="true" />{SCANNER_FOOTER_LEGEND_BOT_QUIET}</span>
      </span>
    </footer>
  );
}
