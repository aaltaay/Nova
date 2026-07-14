import { describe, expect, it } from 'vitest';
import { buildTickerDataSources } from './dataSourceMap';

describe('buildTickerDataSources', () => {
  it('labels broker listing as Alpaca Assets (not the price feed)', () => {
    const rows = buildTickerDataSources({
      discoveryProvider: 'ibkr',
      alpacaFeed: 'iex',
      ibkrConnected: true,
    });
    const listing = rows.find(r => r.role === 'Broker listing');
    expect(listing?.source).toContain('Alpaca');
    expect(listing?.detail?.toLowerCase()).toContain('not prices');
  });

  it('labels Level 2 as IBKR when Gateway is connected', () => {
    const rows = buildTickerDataSources({
      discoveryProvider: 'alpaca',
      alpacaFeed: 'sip',
      ibkrConnected: true,
    });
    expect(rows.find(r => r.role === 'Level 2')?.source).toBe('Interactive Brokers');
  });

  it('switches scanner attribution when discovery_provider changes', () => {
    const alpaca = buildTickerDataSources({
      discoveryProvider: 'alpaca',
      alpacaFeed: 'iex',
      ibkrConnected: false,
    });
    const ibkr = buildTickerDataSources({
      discoveryProvider: 'ibkr',
      alpacaFeed: 'iex',
      ibkrConnected: true,
    });
    expect(alpaca.find(r => r.role === 'Scanner rows')?.source).toBe('Alpaca');
    expect(ibkr.find(r => r.role === 'Scanner rows')?.source).toBe('Interactive Brokers');
  });

  it('mentions the Alpaca IEX/SIP tier on Alpaca-sourced quote rows', () => {
    const rows = buildTickerDataSources({
      discoveryProvider: 'alpaca',
      alpacaFeed: 'sip',
      ibkrConnected: false,
    });
    expect(rows.find(r => r.role === 'Quote & chart')?.source).toContain('SIP');
  });
});
