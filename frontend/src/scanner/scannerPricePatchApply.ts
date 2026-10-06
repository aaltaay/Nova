/** Apply only market price fields and their freshness; halt overlays have their own path. */
import type { ScannerPricePatchRow } from '../hooks/useScannerPriceStream';
import type { ScannerScanAges } from '../utils/scanAge';
import type { ScannerRestSink } from './scannerRestApply';
import { applyHonestPricePatch, normalizePatchRows } from './scannerRowShape';

export function applyScannerPriceRows(
  sink: ScannerRestSink,
  raw: ScannerPricePatchRow[],
  ts: number,
  table?: string | null,
): void {
  // QA C5: the patch is applied inside a state updater, outside the
  // socket's try/catch -- a row without a symbol must never get there.
  const rows = normalizePatchRows(raw);
  if (rows.length === 0) return;
  const apply = (setter: typeof sink.setGappers, ageKey: keyof ScannerScanAges) => {
    setter(prev => applyHonestPricePatch(prev, rows));
    sink.setScanAges(prev => ({ ...prev, [ageKey]: Math.max(prev[ageKey], ts) }));
  };
  // Table-scoped: never let a live Gainers tick mutate a frozen Gappers row.
  if (table === 'gappers') apply(sink.setGappers, 'gappers');
  else if (table === 'gainers') apply(sink.setGainers, 'movers');
  else if (table === 'losers') apply(sink.setLosers, 'movers');
  else if (table === 'afterhours') apply(sink.setAfterhours, 'afterhours');
  else if (table === 'large_cap') apply(sink.setLargeCap, 'largeCap');
  else {
    // Legacy patches without table — apply to all (shadow / older backends).
    sink.setGappers(prev => applyHonestPricePatch(prev, rows));
    sink.setGainers(prev => applyHonestPricePatch(prev, rows));
    sink.setLosers(prev => applyHonestPricePatch(prev, rows));
    sink.setAfterhours(prev => applyHonestPricePatch(prev, rows));
    sink.setScanAges(prev => ({
      ...prev,
      gappers: Math.max(prev.gappers, ts),
      movers: Math.max(prev.movers, ts),
      afterhours: Math.max(prev.afterhours, ts),
    }));
  }
}
