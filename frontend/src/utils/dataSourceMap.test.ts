import { describe, expect, it } from 'vitest';
import { buildTickerDataSources } from './dataSourceMap';

describe('buildTickerDataSources', () => {
  it('labels listing flags as Alpaca metadata (not the price feed)', () => {
    const rows = buildTickerDataSources({
      discoveryProvider: 'ibkr',
      alpacaFeed: 'iex',
      ibkrConnected: true,
    });
    const listing = rows.find(r => r.role === 'Listing flags');
    expect(listing?.source).toContain('Alpaca');
    expect(listing?.detail?.toLowerCase()).toContain('not prices');
  });

  it('labels Level 2 as IBKR when Gateway is connected', () => {
    const rows = buildTickerDataSources({
      discoveryProvider: 'ibkr',
      alpacaFeed: 'sip',
      ibkrConnected: true,
    });
    expect(rows.find(r => r.role === 'Level 2')?.source).toBe('Interactive Brokers');
  });

  it('always attributes scanner rows to IBKR (product lock)', () => {
    const rows = buildTickerDataSources({
      discoveryProvider: 'ibkr',
      alpacaFeed: 'iex',
      ibkrConnected: true,
    });
    expect(rows.find(r => r.role === 'Scanner rows')?.source).toBe('Interactive Brokers');
    expect(rows.find(r => r.role === 'Scanner rows')?.detail?.toLowerCase()).toContain('ibkr');
  });

  it('IBKR quote/chart copy does not advertise Alpaca fallback', () => {
    const rows = buildTickerDataSources({
      discoveryProvider: 'ibkr',
      alpacaFeed: 'iex',
      ibkrConnected: true,
    });
    const quote = rows.find(r => r.role === 'Quote & chart');
    expect(quote?.source).toBe('Interactive Brokers');
    expect(quote?.detail?.toLowerCase()).toContain('no alpaca fallback');
  });
});
