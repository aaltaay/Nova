import { describe, expect, it } from 'vitest';
import { plainPrice, priceDigits, priceStep, roundToTick } from './priceTick';

describe('the listed tick', () => {
  it('is a hundredth of a cent under $1 and a cent from $1 up', () => {
    expect(priceDigits(0.9999)).toBe(4);
    expect(priceDigits(1)).toBe(2);
    expect(priceStep(0.3188)).toBe(0.0001);
    expect(priceStep(1)).toBe(0.01);
  });

  it('rounds on the tick of the price', () => {
    expect(roundToTick(0.31884)).toBe(0.3188);
    expect(roundToTick(5.378)).toBe(5.38);
  });

  it('writes up to four digits and never fewer than two', () => {
    expect(plainPrice(0.3188)).toBe('0.3188');
    expect(plainPrice(0.345)).toBe('0.345');
    expect(plainPrice(0.34)).toBe('0.34');
    expect(plainPrice(0.0404)).toBe('0.0404');
    expect(plainPrice(12.3456)).toBe('12.35');
  });

  it('takes the tick of the stock for a figure that is not its price', () => {
    expect(plainPrice(0.0537, 5.37)).toBe('0.05');
    expect(plainPrice(0.0037, 0.37)).toBe('0.0037');
    expect(roundToTick(0.0537, 5.37)).toBe(0.05);
  });
});
