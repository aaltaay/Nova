/**
 * @vitest-environment jsdom
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { LatencyDashboardView } from './LatencyDashboard';
import { parseLatencyDashboard } from './model';
import {
  REPRESENTATIVE_EXECUTION_PAYLOAD,
  REPRESENTATIVE_OPERATIONS_PAYLOAD,
} from './testFixtures';
import type { BrowserTimingSample } from './types';

afterEach(cleanup);

const SNAPSHOT = parseLatencyDashboard(
  REPRESENTATIVE_OPERATIONS_PAYLOAD,
  REPRESENTATIVE_EXECUTION_PAYLOAD,
  100_000,
);

const BROWSER_SAMPLE: BrowserTimingSample = {
  operation: 'manual_place',
  actionSource: 'user_action',
  outcome: 'ok',
  observedWallMs: 100_000,
  actionToRequestMs: 12,
  requestToResponseMs: 63,
  responseToVisibleMs: 18,
  requestToVisibleMs: 81,
  clockDomain: 'browser_performance_now_same_document',
};

describe('LatencyDashboardView', () => {
  it('renders representative operations, hops, populations, and provenance', () => {
    render(
      <LatencyDashboardView
        snapshot={SNAPSHOT}
        browserSamples={[BROWSER_SAMPLE]}
        loading={false}
        error={null}
        nowWallMs={101_000}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Execution Latency' })).toBeTruthy();
    expect(screen.getByText('http.POST./api/ibkr/order')).toBeTruthy();
    expect(screen.getByText('Ingress → broker ack')).toBeTruthy();
    expect(screen.getByText('Paper')).toBeTruthy();
    expect(screen.getByText('Live')).toBeTruthy();
    expect(screen.getByText('Benchmark · synthetic')).toBeTruthy();
    expect(screen.getByText('execDetails')).toBeTruthy();
    expect(screen.getByText('Target child')).toBeTruthy();
    expect(screen.getByText('Child leg · excluded')).toBeTruthy();
    expect(screen.getByText('manual place')).toBeTruthy();
  });

  it('suppresses mixed aggregate SLA and labels child-leg slippage', () => {
    render(
      <LatencyDashboardView
        snapshot={SNAPSHOT}
        browserSamples={[]}
        loading={false}
        error={null}
        nowWallMs={101_000}
      />,
    );

    expect(screen.getAllByText(/Insufficient/).length).toBeGreaterThan(0);
    expect(screen.getByText('Suppressed')).toBeTruthy();
    expect(screen.getByText(/aggregate percentiles mix normalized populations/)).toBeTruthy();
    expect(screen.getByText(/Use population SLA rows; the aggregate has no verdict/)).toBeTruthy();
    expect(screen.getByText(/browser and backend monotonic values are never subtracted/i)).toBeTruthy();
    expect(screen.getByText(/side-aware fill-leg aggregates are shown/i)).toBeTruthy();
    expect(screen.getByText('Pass')).toBeTruthy();
  });

  it('renders stale and partial-error states without hiding last-good data', () => {
    render(
      <LatencyDashboardView
        snapshot={SNAPSHOT}
        browserSamples={[]}
        loading={false}
        error="Partial data: execution endpoint returned HTTP 503"
        nowWallMs={130_000}
      />,
    );

    expect(screen.getByRole('alert').textContent).toContain('Partial data');
    expect(screen.getByText(/Stale dashboard fetch/)).toBeTruthy();
    expect(screen.getByText('Process-local operation metrics')).toBeTruthy();
  });
});
