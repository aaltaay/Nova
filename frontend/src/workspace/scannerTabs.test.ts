import { describe, expect, it } from 'vitest';
import { declaresScannerL1, isMainScannerTab } from './scannerTabs';

describe('scannerTabs Volume boost', () => {
  it('is a main scanner tab that must not steal the active L1 table', () => {
    expect(isMainScannerTab('volume_boost')).toBe(true);
    expect(declaresScannerL1('volume_boost')).toBe(false);
    expect(declaresScannerL1('gainers')).toBe(true);
    expect(declaresScannerL1('large_cap')).toBe(true);
  });
});
