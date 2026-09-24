/** @vitest-environment jsdom */
/** Click-to-sort on the population segment table: Pass above Fail, no verdict last both ways. */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { SegmentTable } from './LatencyTables';
import type { ExecutionSegmentSummary } from './types';

afterEach(() => {
  cleanup();
  localStorage.clear();
});

function segment(ackP95: number, status: string | null): ExecutionSegmentSummary {
  return {
    sampleCount: 24,
    errorCount: 0,
    distributions: {
      broker_ack_ms: {
        count: 24, errorCount: 0, p50: ackP95 / 2, p95: ackP95, p99: ackP95, max: ackP95,
        sufficient: true, minimumSamples: 20, excludedCount: 0, excludedReasons: {},
      },
    },
    sla: status == null
      ? null
      : { targetP95Ms: 100, p95Ms: ackP95, pass: status === 'pass', status, evidenceSufficient: true },
  };
}

const SEGMENTS = {
  paper: segment(80, 'fail'),
  live: segment(60, null),
  benchmark_synthetic: segment(40, 'pass'),
};

const order = () =>
  screen.getAllByRole('row').slice(1).map(r => (r as HTMLTableRowElement).cells[0].textContent);
const header = (name: string) => screen.getByRole('columnheader', { name });

describe('SegmentTable sorting', () => {
  it('sorts the population SLA pass first and keeps no verdict last', () => {
    render(<SegmentTable title="Population" segments={SEGMENTS} population />);
    act(() => fireEvent.click(header('Population SLA')));
    expect(order()).toEqual(['Benchmark · synthetic', 'Paper', 'Live']);
    act(() => fireEvent.click(header('Population SLA')));
    expect(order()).toEqual(['Paper', 'Benchmark · synthetic', 'Live']);
  });

  it('sorts Ack p95 on the number, slowest first', () => {
    render(<SegmentTable title="Population" segments={SEGMENTS} population />);
    act(() => fireEvent.click(header('Ack p95')));
    expect(order()).toEqual(['Paper', 'Live', 'Benchmark · synthetic']);
  });
});
