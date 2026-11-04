import { describe, expect, it } from 'vitest';
import { SHORT_WHY_FLAT_SELL } from '../constantGroups/short_ticket';
import { sideButtons } from './shortTicketModel';

const sell = (botsQty: number | undefined, qty: number | null = 0) =>
  sideButtons({ symbol: 'ORCL', qty, known: true, allowShort: true, shortBlock: null, botsQty })
    .find((b) => b.side === 'sell');

describe("the ticket's Sell lock names the bots' shares (ADR 069 decision 9)", () => {
  it('says where the shares are when you are flat and the bots are long', () => {
    expect(sell(40)?.lock).toBe(`${SHORT_WHY_FLAT_SELL('ORCL')} The 40 shares are the bots' -- Close on their row sells them.`);
  });

  it('keeps the refusal as it was while the bots hold none, or hold short', () => {
    expect(sell(undefined)?.lock).toBe(SHORT_WHY_FLAT_SELL('ORCL'));
    expect(sell(0)?.lock).toBe(SHORT_WHY_FLAT_SELL('ORCL'));
    expect(sell(-19)?.lock).toBe(SHORT_WHY_FLAT_SELL('ORCL'));
  });

  it('never opens Sell because the bots hold shares', () => {
    expect(sell(40)?.lock).toBeTruthy();
  });

  it('leaves your long alone: the sides follow your shares, never theirs', () => {
    expect(sell(40, 100)?.lock).toBeNull();
  });
});
