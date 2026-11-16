import { describe, expect, it } from 'vitest';
import { ownerHoldSentence } from '../constantGroups/owners';
import { SHORT_WHY_FLAT_SELL } from '../constantGroups/short_ticket';
import type { OwnerHold } from './deskPositions';
import { sideButtons } from './shortTicketModel';

const sell = (othersHold: OwnerHold | null | undefined, qty: number | null = 0) =>
  sideButtons({ symbol: 'ORCL', qty, known: true, allowShort: true, shortBlock: null, othersHold })
    .find((b) => b.side === 'sell');

describe("the ticket's Sell lock names the trader whose shares they are (ADR 072)", () => {
  it('says whose the shares are when you are flat and another trader is long', () => {
    expect(sell({ owner: 'brain', qty: 40 })?.lock).toBe(SHORT_WHY_FLAT_SELL('ORCL') + ownerHoldSentence('brain', 40));
    expect(sell({ owner: 'claude', qty: 300 })?.lock)
      .toBe(`${SHORT_WHY_FLAT_SELL('ORCL')} The 300 shares are Claude's -- switch Claude off to close them yourself.`);
  });

  it('keeps the refusal as it was while nobody else holds it, or holds it short', () => {
    expect(sell(undefined)?.lock).toBe(SHORT_WHY_FLAT_SELL('ORCL'));
    expect(sell(null)?.lock).toBe(SHORT_WHY_FLAT_SELL('ORCL'));
    expect(sell({ owner: 'claude', qty: -19 })?.lock).toBe(SHORT_WHY_FLAT_SELL('ORCL'));
  });

  it("never opens Sell because another trader holds shares", () => {
    expect(sell({ owner: 'claude', qty: 40 })?.lock).toBeTruthy();
  });

  it('leaves your long alone: the sides follow your shares, never theirs', () => {
    expect(sell({ owner: 'claude', qty: 40 }, 100)?.lock).toBeNull();
  });
});
