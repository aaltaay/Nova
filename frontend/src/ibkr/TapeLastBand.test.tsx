/** @vitest-environment jsdom */
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { TapeLastBand } from './TapeLastBand';
import { reloadLevel2SizeForTesting, setLevel2Size } from './level2Size';
import type { TapePrint } from './tapeFeed';

afterEach(cleanup);

const print = (over: Partial<TapePrint> = {}): TapePrint => ({
  symbol: 'SPY', time: '2026-09-30T13:41:30Z', price: 4.33, size: 700, exchange: 'ARCA', side: 'ask', ...over,
});

describe('the Last band over the tape', () => {
  beforeEach(() => {
    localStorage.clear();
    reloadLevel2SizeForTesting();
  });

  it("shows the newest print's price in its side's colour and its size", () => {
    const { getByTestId } = render(<TapeLastBand print={print()} />);
    expect(getByTestId('ts-last-price').textContent).toBe('4.33');
    expect(getByTestId('ts-last-price').className).toContain('ts-last__price--ask');
    expect(getByTestId('ts-last-size').textContent).toBe('700');
  });

  it('colours a print at the bid red and a print between the quotes neither', () => {
    const { getByTestId, rerender } = render(<TapeLastBand print={print({ side: 'bid', price: 0.7824, size: 12500 })} />);
    expect(getByTestId('ts-last-price').className).toContain('ts-last__price--bid');
    expect(getByTestId('ts-last-price').textContent).toBe('0.7824');
    expect(getByTestId('ts-last-size').textContent).toBe('12,500');
    rerender(<TapeLastBand print={print({ side: 'between' })} />);
    expect(getByTestId('ts-last-price').className).toContain('ts-last__price--mid');
  });

  it('keeps its place with a dash while the tape has no print', () => {
    const { getByTestId, queryByTestId } = render(<TapeLastBand print={null} />);
    expect(getByTestId('ts-last-price').textContent).toBe('—');
    expect(queryByTestId('ts-last-size')).toBeNull();
  });

  it('follows the Level 2 size', () => {
    const { getByTestId } = render(<TapeLastBand print={print()} />);
    expect(getByTestId('ts-last').getAttribute('data-l2-size')).toBe('large');
    act(() => setLevel2Size('small'));
    expect(getByTestId('ts-last').getAttribute('data-l2-size')).toBe('small');
  });
});
