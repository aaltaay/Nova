/**
 * The Cryptos page's sample board, told as the desk's morning (ADR 043). The shared sample
 * (cryptos/sampleCryptos.ts) is the night before at 23:08 ET with US stocks closed; on the demo the
 * header says 09:41 and the market is open, so the clock, the next events and the sources' ages
 * follow the demo clock. Prices, flows and news stay the sample's. Nova Marketing Sample Data.
 */
import { SAMPLE_CRYPTO_BOARD } from '../../cryptos/sampleCryptos';
import type { CryptoBoard } from '../../cryptos/types';
import { etMs } from './market';

const at = (h: number, m = 0) => etMs(h, m) / 1000;

export function cryptoBoard(nowS: number): CryptoBoard {
  const b = SAMPLE_CRYPTO_BOARD;
  const shift = nowS - b.clock.now;
  const fearGreed = b.market.fear_greed;
  return {
    ...b,
    generated_at: nowS,
    clock: {
      ...b.clock,
      now: nowS,
      stock_session: 'regular',
      stock_next: { kind: 'close', at: at(16) },
      regions: { asia: false, europe: true, us: true },
      next_funding: at(12),
    },
    market: { ...b.market, fear_greed: fearGreed ? { ...fearGreed, at: fearGreed.at == null ? null : fearGreed.at + shift } : null },
    bridge: { ...b.bridge, phase: 'regular' },
    next: [
      { at: at(12), kind: 'funding', title: 'Funding settles', detail: 'The 8-hour futures exchanges settle funding at 00:00, 08:00 and 16:00 UTC.' },
      { at: at(16), kind: 'stocks', title: 'US stocks close', detail: null },
      { at: at(20), kind: 'crypto_day', title: 'New crypto day', detail: 'Daily candles and 24-hour changes on most sites reset at 00:00 UTC.' },
      { at: Date.UTC(2026, 9, 2, 8, 0) / 1000, kind: 'expiry', title: 'Weekly options expiry', detail: 'BTC $4.1B open on Deribit' },
    ],
    sources: b.sources.map((s) => ({ ...s, at: s.at == null ? null : s.at + shift })),
  };
}
