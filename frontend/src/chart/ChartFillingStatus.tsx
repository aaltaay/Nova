/**
 * What a filling chart pane says (ADR 012, #555): IBKR history is loading, or
 * IBKR stopped answering and the pane is retrying. The reason is the `/bars`
 * coverage's `last_error`, the backend's own words -- nothing here guesses one.
 */
import { formatCoverageClockEt } from '../tickerChartData';

export const CHART_FILLING_TEXT = 'Loading IBKR historical…';
export const CHART_FILLING_HINT = 'filling…';
export const CHART_HISTORY_RETRYING_TEXT = 'IBKR history did not answer — retrying';
/** Shorter for the pane header, which holds one line. */
export const CHART_HISTORY_RETRYING_HINT = 'IBKR did not answer, retrying…';

function failureClockEt(lastErrorTs: number | null | undefined): string | null {
  if (lastErrorTs == null || !Number.isFinite(lastErrorTs)) return null;
  return formatCoverageClockEt(new Date(lastErrorTs * 1000).toISOString());
}

/** The header hint on a pane that already painted bars and is still filling. */
export function chartFillingHint(
  coverageClock: string | null,
  lastError: string | null | undefined,
): string {
  const status = lastError ? CHART_HISTORY_RETRYING_HINT : CHART_FILLING_HINT;
  return coverageClock ? `as of ${coverageClock} ET, ${status}` : status;
}

/** The overlay on a pane that is filling with no bars yet. */
export function ChartFillingOverlay({
  lastError,
  lastErrorTs,
}: {
  lastError: string | null | undefined;
  lastErrorTs?: number | null;
}) {
  if (!lastError) {
    return <div className="chart-overlay chart-overlay--info">{CHART_FILLING_TEXT}</div>;
  }
  const clock = failureClockEt(lastErrorTs);
  return (
    <div
      className="chart-overlay chart-overlay--info chart-overlay--retrying"
      role="status"
      data-testid="chart-history-retrying"
    >
      <span>{CHART_HISTORY_RETRYING_TEXT}</span>
      <span className="chart-overlay-detail">
        {clock ? `${lastError} (${clock} ET)` : lastError}
      </span>
    </div>
  );
}
