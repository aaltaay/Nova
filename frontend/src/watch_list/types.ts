/** Shapes the watch list shares with its hosts. */
import type { ScannerRow } from '../types/scanner';

/** The boards a watched symbol is looked up on, in the order a row is taken from. */
export interface WatchListBoards {
  gainers: readonly ScannerRow[];
  gappers: readonly ScannerRow[];
  losers: readonly ScannerRow[];
  afterhours: readonly ScannerRow[];
  largeCap: readonly ScannerRow[];
}
