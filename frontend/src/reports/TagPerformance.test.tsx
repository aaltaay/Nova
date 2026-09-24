/** @vitest-environment jsdom */
/** Click-to-sort on the Tag performance table: a header sorts, and an unknown win rate stays last. */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { TagPerformance } from './TagPerformance';
import type { TagPerformanceRow, TagsResponse } from './types';

afterEach(() => {
  cleanup();
  localStorage.clear();
});

function tag(name: string, pnl: number, winRate: number | null): TagPerformanceRow {
  return { tag: name, count: 3, wins: 1, losses: 1, flat: 1, win_rate_pct: winRate, pnl };
}

const DATA: TagsResponse = {
  includes_mock_data: false,
  count: 3,
  tags: [tag('momentum', 120, 60), tag('reversal', -40, null), tag('breakout', 300, 75)],
};

const order = () =>
  screen.getAllByRole('row').slice(1).map(r => (r as HTMLTableRowElement).cells[0].textContent);
const header = (name: string) => screen.getByRole('columnheader', { name });

describe('TagPerformance sorting', () => {
  it('sorts P&L highest first, then lowest first, then back to the server order', () => {
    render(<TagPerformance data={DATA} loading={false} />);
    expect(order()).toEqual(['momentum', 'reversal', 'breakout']);
    act(() => fireEvent.click(header('P&L')));
    expect(order()).toEqual(['breakout', 'momentum', 'reversal']);
    act(() => fireEvent.click(header('P&L')));
    expect(order()).toEqual(['reversal', 'momentum', 'breakout']);
    act(() => fireEvent.click(header('P&L')));
    expect(order()).toEqual(['momentum', 'reversal', 'breakout']);
  });

  it('keeps an unknown win rate last both ways and sorts tags A to Z', () => {
    render(<TagPerformance data={DATA} loading={false} />);
    act(() => fireEvent.click(header('Win rate')));
    expect(order()).toEqual(['breakout', 'momentum', 'reversal']);
    act(() => fireEvent.click(header('Win rate')));
    expect(order()).toEqual(['momentum', 'breakout', 'reversal']);
    act(() => fireEvent.click(header('Tag')));
    expect(order()).toEqual(['breakout', 'momentum', 'reversal']);
    expect(header('Tag').getAttribute('aria-sort')).toBe('ascending');
  });
});
