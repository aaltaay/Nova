/**
 * Float and short interest as the desk shows them: with their date and basis (#532).
 *
 * Every figure is Yahoo's (backend `fundamentals.py`). Short interest is FINRA's, reported twice a
 * month about two weeks late, so it carries its settlement date. Yahoo's short ratio divides it by
 * Yahoo's own average volume and is not FINRA's days to cover. Yahoo's float is the last filing's
 * share count less insiders; when Yahoo's own shares outstanding or short interest contradicts it
 * (`float_contradicted`), the float reads "54.0K?" and says why. Descriptive only: no gate reads it.
 */

/** Appended to a float Yahoo's own share counts contradict: "54.0K?". */
export const FLOAT_CONTRADICTED_MARK = '?';
/** The tooltip when the backend flagged a float but sent no reason. */
export const FLOAT_CONTRADICTED_FALLBACK =
  "Yahoo's own shares outstanding or short interest contradict this float -- likely stale since a dilution";
/** Where a short-interest figure comes from. */
export const SHORT_INTEREST_SOURCE = 'Yahoo, from FINRA (reported twice a month, about two weeks late)';
export const SHORT_INTEREST_NO_DATE = 'settlement date not reported';
/** The scanner's second line when only Yahoo's short ratio is known. */
export const SHORT_RATIO_CELL_SUFFIX = ' ratio';
/** The quote panel's label for Yahoo's short ratio. */
export const SHORT_RATIO_YAHOO_LABEL = 'Short Ratio (Yahoo)';
export const shortRatioTitle = (ratio: string): string =>
  `Short ratio ${ratio} is Yahoo's own: short interest over Yahoo's average daily volume, not FINRA's days to cover.`;
