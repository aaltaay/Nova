import { describe, expect, it } from 'vitest';
import {
  isAlertDockMode,
  isHodDockMode,
  isRosterDockMode,
  SCANNER_DOCK_MODE_LABEL,
  SCANNER_DOCK_ROSTER_MODES,
} from './scannerDockModes';

describe('scannerDockModes', () => {
  it('keeps HOD / Running Up as alert modes', () => {
    expect(isAlertDockMode('hod_momo')).toBe(true);
    expect(isAlertDockMode('running_up')).toBe(true);
    expect(isAlertDockMode('gappers')).toBe(false);
  });

  it('treats IBKR roster tables as dock siblings', () => {
    expect([...SCANNER_DOCK_ROSTER_MODES]).toEqual([
      'gappers',
      'gainers',
      'losers',
      'afterhours',
      'catalysts',
    ]);
    expect(isRosterDockMode('gappers')).toBe(true);
    expect(isRosterDockMode('hod_momo')).toBe(false);
    expect(isHodDockMode('afterhours')).toBe(true);
    expect(SCANNER_DOCK_MODE_LABEL.afterhours).toBe('AH');
  });
});
