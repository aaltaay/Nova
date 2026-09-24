/**
 * @vitest-environment jsdom
 *
 * #555: when IBKR's historical farm stopped answering (2026-09-23 21:46 ET)
 * every pane said "Loading IBKR historical…" for the whole outage.
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import {
  CHART_FILLING_TEXT,
  CHART_HISTORY_RETRYING_TEXT,
  ChartFillingOverlay,
  chartFillingHint,
} from './ChartFillingStatus';

const TIMEOUT = 'IBKR historical data did not answer within 20s';
// 2026-09-24 01:46:00 UTC = 21:46 ET.
const AT_2146_ET = Date.parse('2026-09-24T01:46:00Z') / 1000;

afterEach(cleanup);

describe('ChartFillingOverlay', () => {
  it('says loading while no failure is stated', () => {
    render(<ChartFillingOverlay lastError={null} />);
    expect(screen.getByText(CHART_FILLING_TEXT)).toBeTruthy();
    expect(screen.queryByTestId('chart-history-retrying')).toBeNull();
  });

  it('says IBKR history did not answer, with the reason and when', () => {
    render(<ChartFillingOverlay lastError={TIMEOUT} lastErrorTs={AT_2146_ET} />);
    const overlay = screen.getByTestId('chart-history-retrying');
    expect(overlay.textContent).toContain(CHART_HISTORY_RETRYING_TEXT);
    expect(overlay.textContent).toContain(`${TIMEOUT} (21:46 ET)`);
    expect(screen.queryByText(CHART_FILLING_TEXT)).toBeNull();
  });

  it('states the reason without a time when none was sent', () => {
    render(<ChartFillingOverlay lastError={TIMEOUT} lastErrorTs={null} />);
    expect(screen.getByText(TIMEOUT)).toBeTruthy();
  });
});

describe('chartFillingHint', () => {
  it('keeps the plain filling hint without a failure', () => {
    expect(chartFillingHint('09:31', null)).toBe('as of 09:31 ET, filling…');
    expect(chartFillingHint(null, undefined)).toBe('filling…');
  });

  it('says a painted pane is retrying after IBKR did not answer', () => {
    expect(chartFillingHint('09:31', TIMEOUT)).toBe('as of 09:31 ET, IBKR did not answer, retrying…');
    expect(chartFillingHint(null, TIMEOUT)).toBe('IBKR did not answer, retrying…');
  });
});
