/**
 * Publish scanner/catalyst headline timestamps for HOD News flame join.
 */
import { useEffect } from 'react';
import {
  setScannerNews,
  type ScannerNewsSource,
} from '../components/scannerNewsStore';
import type { CatalystVerdict } from '../types/catalystVerdict';
import { buildCatalystBySymbol, buildNewsBySymbol } from './newsBySymbol';

type NewsRow = { symbol: string; newest_headline_at: string | null; catalyst?: CatalystVerdict | null };

export function usePublishScannerNews(opts: {
  source: ScannerNewsSource;
  gappers: NewsRow[];
  gainers: NewsRow[];
  losers: NewsRow[];
  afterhours: NewsRow[];
  catalysts: NewsRow[];
  /** When true (history mode), publish empty so past headlines do not decorate live alerts. */
  clear?: boolean;
}): void {
  const {
    source,
    gappers,
    gainers,
    losers,
    afterhours,
    catalysts,
    clear = false,
  } = opts;

  useEffect(() => {
    if (clear) {
      setScannerNews(source, new Map());
      return;
    }
    const rows = [...gappers, ...gainers, ...losers, ...afterhours, ...catalysts];
    setScannerNews(source, buildNewsBySymbol(rows), buildCatalystBySymbol(rows));
  }, [source, gappers, gainers, losers, afterhours, catalysts, clear]);
}
