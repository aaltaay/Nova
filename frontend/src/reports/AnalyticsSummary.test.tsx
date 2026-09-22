/** @vitest-environment jsdom */
/** QA D25: "WINNING DAYS 0" was green and "LOSING DAYS 0" red on the Account page's Reports tab. */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { AnalyticsSummary } from './AnalyticsSummary';
import type { YearCalendarResponse } from './types';

afterEach(cleanup);

function data(winning: number, losing: number): YearCalendarResponse {
  return {
    year_pnl: 0, year_trade_count: 0, winning_days: winning, losing_days: losing, best_day: null, worst_day: null,
  } as unknown as YearCalendarResponse;
}

describe('AnalyticsSummary', () => {
  it('leaves zero counts untinted', () => {
    render(<AnalyticsSummary data={data(0, 0)} />);
    expect(screen.getByTestId('reports-winning-days').className).toBe('');
    expect(screen.getByTestId('reports-losing-days').className).toBe('');
  });

  it('tints real counts', () => {
    render(<AnalyticsSummary data={data(3, 1)} />);
    expect(screen.getByTestId('reports-winning-days').className).toBe('pnl-pos');
    expect(screen.getByTestId('reports-losing-days').className).toBe('pnl-neg');
  });
});
