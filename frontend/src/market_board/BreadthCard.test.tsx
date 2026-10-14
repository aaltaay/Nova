/**
 * @vitest-environment jsdom
 *
 * NYSE breadth in words (operator ask 2026-10-14: "I don't understand the numbers. What is 1,540?"): the card says
 * what share of stocks and of volume is rising, and reads TICK and TRIN as sentences.
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { BreadthCard } from './BreadthCard';
import type { Breadth } from './types';

const AT = Date.UTC(2026, 9, 13, 19, 0) / 1000;

function breadth(over: Partial<Breadth> = {}): Breadth {
  return {
    state: 'ok', why: null, at: AT, data_type: 'live', advancing: 1540, declining: 1226, unchanged: 96,
    up_volume: 480, down_volume: 520, tick: -146, trin: 1.35, ad_line: [[AT - 600, 200], [AT, 314]],
    line_since: AT - 600, prior: null, ...over,
  };
}

afterEach(cleanup);

describe('the breadth card in words', () => {
  it('says what share of NYSE stocks and of the volume is rising', () => {
    render(<BreadthCard breadth={breadth()} />);
    expect(screen.getByTestId('market-breadth-lede').textContent)
      .toBe('56% of NYSE stocks are up on the day, and 48% of the shares traded were in rising stocks.');
    const card = screen.getByTestId('market-breadth').textContent ?? '';
    expect(card).toContain('1,540 up');
    expect(card).toContain('1,226 down');
    expect(card).toContain('of 2,862 NYSE stocks, 96 unchanged');
    expect(card).toContain('52% falling');
  });

  it('reads TICK and TRIN as sentences', () => {
    render(<BreadthCard breadth={breadth()} />);
    const card = screen.getByTestId('market-breadth').textContent ?? '';
    expect(card).toContain('146 more stocks just ticked down than up');
    expect(card).toContain('sellers heavier');
    expect(card).toContain('+314 now');
  });

  it('says buyers are heavier under 1 and an upticking market', () => {
    render(<BreadthCard breadth={breadth({ tick: 412, trin: 0.74 })} />);
    const card = screen.getByTestId('market-breadth').textContent ?? '';
    expect(card).toContain('412 more stocks just ticked up than down');
    expect(card).toContain('buyers heavier');
  });

  it('says it has no count yet instead of a zero', () => {
    render(<BreadthCard breadth={breadth({ advancing: null, declining: null, up_volume: null, down_volume: null })} />);
    expect(screen.getByTestId('market-breadth-lede').textContent).toBe('No count of rising and falling NYSE stocks yet.');
  });
});
