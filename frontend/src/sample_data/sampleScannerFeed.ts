/**
 * The sample rows as the scanner feed the Focus rail and the Desk board read
 * (#449). The live desk's feed comes from ScannerDataProvider (roster fetch,
 * `/ws/scanner`, IBKR L1 lines); the sample desk has none of that, so this is
 * the same shape over fixed rows, with no L1 line to declare -- the list
 * setters do nothing.
 */
import { makeLiveScannerFeedStub, type LiveScannerFeed } from '../scanner/ScannerDataContext';
import type { SampleDataBundle } from './SampleDataContext';

export function sampleScannerFeed(
  sample: SampleDataBundle,
  nowSec: number = Math.floor(Date.now() / 1000),
): LiveScannerFeed {
  return makeLiveScannerFeedStub({
    health: sample.health,
    gappers: sample.gappers,
    gainers: sample.gainers,
    losers: sample.losers,
    afterhours: sample.afterhours,
    largeCap: sample.largeCap,
    catalysts: sample.catalysts,
    now: nowSec,
    pricesStale: false,
  });
}
