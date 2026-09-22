/**
 * @vitest-environment jsdom
 *
 * Reports' first poll (QA V42, 2026-09-22): the calendar sat on "Loading
 * calendar…" for a whole poll interval (15 s) because a shared in-flight
 * flag let the first effect run's discarded request block the next run's
 * first poll -- which StrictMode's double mount always triggers.
 */
import { StrictMode } from 'react';
import { act } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REPORTS_SOURCE_NOTE } from './importConstants';
import { useCalendar } from './useCalendar';

function Probe() {
  const { yearData, loading } = useCalendar(true, 2026, null, false, 0);
  return <div data-testid="probe">{loading ? 'loading' : `trades:${yearData?.year_trade_count ?? 'none'}`}</div>;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('useCalendar', () => {
  it('answers from the first poll, even under StrictMode', async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    vi.stubGlobal('fetch', vi.fn(async () => {
      await gate;
      return { ok: true, json: async () => ({ year: 2026, year_trade_count: 3, months: [] }) };
    }));
    render(<StrictMode><Probe /></StrictMode>);
    await act(async () => {
      release();
      for (let i = 0; i < 10; i += 1) await Promise.resolve();
    });
    expect(screen.getByTestId('probe').textContent).toBe('trades:3');
  });

  it('the Reports tab says which calendar this is', () => {
    expect(REPORTS_SOURCE_NOTE).toMatch(/trade journal/);
    expect(REPORTS_SOURCE_NOTE).toMatch(/Account page/);
  });
});
