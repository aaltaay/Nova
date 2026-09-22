/**
 * Remove a lightweight-charts instance only after the rest of this React
 * commit's cleanups have run.
 *
 * React destroys a parent's effects before its children's. The pane's
 * `useChartInstance` (parent) used to call `chart.remove()` first; the
 * overlays below it (indicator series, drawings, session highlight) then
 * called `removeSeries` / `detachPrimitive` on the removed chart, which
 * scheduled a redraw the removed chart could no longer cancel. The next frame
 * drew into disposed canvases: uncaught "Object is disposed" on every Trader
 * tab close, pop-out, 10-Second / MACD toggle and replay seek (QA V19, R30).
 *
 * A microtask runs after every cleanup of the current commit and before the
 * next frame, so the children tidy up against a live chart and `remove()` then
 * cancels whatever redraw they queued.
 */
import type { IChartApi } from 'lightweight-charts';

export function removeChartAfterCleanups(chart: Pick<IChartApi, 'remove'>): void {
  queueMicrotask(() => {
    try {
      chart.remove();
    } catch (err) {
      console.warn('[Nova] chart remove failed', err);
    }
  });
}
