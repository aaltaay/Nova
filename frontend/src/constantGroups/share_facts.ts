/**
 * Float and short interest as the desk shows them: with their date and basis (#532).
 *
 * Every figure is Yahoo's (backend `fundamentals.py`). Short interest is FINRA's, reported twice a
 * month about two weeks late, so it carries its settlement date. Yahoo's short ratio divides it by
 * Yahoo's own average volume and is not FINRA's days to cover. Yahoo's float is the last filing's
 * share count less insiders; when Yahoo's own shares outstanding contradicts it (`float_contradicted`),
 * the float reads "54.0K?" and says why. The backend's max-float gates pass such a float only on
 * shares outstanding (`strategy/float_gate.py`). More shares short than the float
 * (`short_above_float`) is a warning only -- a stale float and heavy shorting look the same -- so the
 * short interest reads "9.0M!" in amber and no gate reads it. The scanner's Float chip is a view
 * filter that keeps what it cannot judge, so it still compares the float as shown.
 */

/** Appended to a float Yahoo's own share counts contradict: "54.0K?". */
export const FLOAT_CONTRADICTED_MARK = '?';
/** The tooltip when the backend flagged a float but sent no reason. */
export const FLOAT_CONTRADICTED_FALLBACK =
  "Yahoo's own shares outstanding contradicts this float -- likely stale since a dilution";
/** Appended to short interest above the float: "9.0M!" -- a warning, never a gate. */
export const SHORT_ABOVE_FLOAT_MARK = '!';
/** The class that colours that warning amber. */
export const SHORT_ABOVE_FLOAT_CLASS = 'short-above-float';
/** The warning when the backend flagged it but sent no reason. */
export const SHORT_ABOVE_FLOAT_FALLBACK =
  'Short interest is above the float -- either the float is stale or shares were lent more than once '
  + '(heavy shorting). A warning only: no gate reads it';
/** Where a short-interest figure comes from. */
export const SHORT_INTEREST_SOURCE = 'Yahoo, from FINRA (reported twice a month, about two weeks late)';
export const SHORT_INTEREST_NO_DATE = 'settlement date not reported';
/** The scanner's second line when only Yahoo's short ratio is known. */
export const SHORT_RATIO_CELL_SUFFIX = ' ratio';
/** The quote panel's label for Yahoo's short ratio. */
export const SHORT_RATIO_YAHOO_LABEL = 'Short Ratio (Yahoo)';
export const shortRatioTitle = (ratio: string): string =>
  `Short ratio ${ratio} is Yahoo's own: short interest over Yahoo's average daily volume, not FINRA's days to cover.`;
