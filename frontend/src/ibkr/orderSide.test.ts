import { describe, expect, it } from 'vitest';
import { flattenLabel, liquidationTitle, orderSideSortKey, orderSideWords, positionSideWords } from './orderSide';
import { orderSentBy } from './orderSentBy';

describe('the Side column (ADR 048)', () => {
  it('names the side and what the order does to it, from the row itself', () => {
    expect(orderSideWords({ side: 'SELL', position_side: 'short', effect: 'opens' }).label).toBe('Short · Sell · opens');
    expect(orderSideWords({ side: 'BUY', position_side: 'short', effect: 'closes' }).label).toBe('Short · Buy · closes');
    expect(orderSideWords({ side: 'BUY', position_side: 'long', effect: 'opens' }).label).toBe('Long · Buy · opens');
    expect(orderSideWords({ side: 'SELL', position_side: 'long', effect: 'closes' }).label).toBe('Long · Sell · closes');
  });

  it('reads a short entry from an older row and never guesses a row with no record', () => {
    const older = orderSideWords({ side: 'SELL', short_entry: true });
    expect([older.tag, older.effect]).toEqual(['SHORT', 'opens']);
    const unknown = orderSideWords({ side: 'BUY' });
    expect([unknown.tag, unknown.tone, unknown.effect]).toEqual(['?', 'unknown', null]);
    expect(unknown.tip).toMatch(/never guesses/);
  });

  it('sorts long before short, opens before closes, and an unknown side last', () => {
    const keys = [
      orderSideSortKey({ side: 'BUY', position_side: 'short', effect: 'closes' }),
      orderSideSortKey({ side: 'SELL', position_side: 'long', effect: 'closes' }),
      orderSideSortKey({ side: 'SELL', position_side: 'short', effect: 'opens' }),
      orderSideSortKey({ side: 'BUY', position_side: 'long', effect: 'opens' }),
    ];
    expect([...keys].sort()).toEqual([keys[3], keys[1], keys[2], keys[0]]);
    expect(orderSideSortKey({ side: 'BUY' })).toBe('');
  });

  it('labels a position and a short flatten as a cover', () => {
    expect(positionSideWords({ qty: -416 }).tag).toBe('SHORT');
    expect(positionSideWords({ qty: 300, position_side: 'long' }).note).toBe('shares you own');
    expect(positionSideWords({ qty: 0 }).tone).toBe('unknown');
    expect(flattenLabel(-416, 'Flatten')).toBe('Flatten 416 (cover)');
    expect(flattenLabel(300, 'Flatten')).toBe('Flatten 300');
  });

  it('says where IBKR would liquidate, or why it cannot say', () => {
    expect(liquidationTitle({ liquidation_price: 9, liquidation_source: 'published rules' })).toMatch(
      /near 9\.00.*published rules/,
    );
    expect(liquidationTitle({ liquidation_price: null })).toMatch(/not known/);
  });

  it("names Nova's own closes in Sent by", () => {
    expect(orderSentBy({ order_origin: 'day_cover', order_source: 'flatten' })).toMatchObject({
      label: 'Day cover',
      tone: 'breaker',
    });
    expect(orderSentBy({ order_origin: 'margin_call', order_source: 'flatten' }).label).toBe('Margin call');
  });
});
