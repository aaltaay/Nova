/**
 * Publish scanner/catalyst headline timestamps for HOD News flame join.
 */
import { useEffect } from 'react';
import {
  setScannerNews,
  type ScannerNewsSource,
} from '../components/scannerNewsStore';
import { buildNewsBySymbol } from './newsBySymbol';

type NewsRow = { symbol: string; newest_headline_at: string | null };

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
    setScannerNews(
      source,
      buildNewsBySymbol([
        ...gappers,
        ...gainers,
        ...losers,
        ...afterhours,
        ...catalysts,
      ]),
    );
  }, [source, gappers, gainers, losers, afterhours, catalysts, clear]);
}
