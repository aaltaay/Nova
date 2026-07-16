import { describe, expect, it } from 'vitest';
import { scanAgeForTab } from './scanAge';

describe('scanAgeForTab', () => {
  const ages = { gappers: 100, movers: 200, afterhours: 10 };

  it('uses the active scanner tab timestamp', () => {
    expect(scanAgeForTab('gappers', ages)).toBe(100);
    expect(scanAgeForTab('movers', ages)).toBe(200);
    expect(scanAgeForTab('gainers', ages)).toBe(200);
    expect(scanAgeForTab('losers', ages)).toBe(200);
    expect(scanAgeForTab('afterhours', ages)).toBe(10);
  });

  it('falls back to the freshest age for non-scanner tabs', () => {
    expect(scanAgeForTab('watchlist', ages)).toBe(200);
    expect(scanAgeForTab('trading', ages)).toBe(200);
  });

  it('does not let a frozen after-hours stamp age the Movers tab', () => {
    // Regression: fetchData used to overwrite lastScan with afterhours last,
    // producing "updated 5962s ago" while /api/movers was seconds fresh.
    const closedSession = {
      gappers: 1_780_000_100,
      movers: 1_780_000_200,
      afterhours: 1_780_000_200 - 5962,
    };
    expect(scanAgeForTab('movers', closedSession)).toBe(closedSession.movers);
    expect(scanAgeForTab('movers', closedSession)).toBeGreaterThan(
      scanAgeForTab('afterhours', closedSession),
    );
  });

  it('still reports the frozen after-hours age on the After Hours tab', () => {
    const closedSession = { gappers: 50, movers: 60, afterhours: 10 };
    expect(scanAgeForTab('afterhours', closedSession)).toBe(10);
  });
});
