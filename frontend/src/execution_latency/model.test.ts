import { describe, expect, it } from 'vitest';
import {
  isLatencySnapshotStale,
  parseLatencyDashboard,
  populationLabel,
} from './model';
import {
  REPRESENTATIVE_EXECUTION_PAYLOAD,
  REPRESENTATIVE_OPERATIONS_PAYLOAD,
} from './testFixtures';

describe('latency dashboard model', () => {
  it('parses bounded operations, distributions, and provenance', () => {
    const parsed = parseLatencyDashboard(
      REPRESENTATIVE_OPERATIONS_PAYLOAD,
      REPRESENTATIVE_EXECUTION_PAYLOAD,
      10_000,
    );

    expect(parsed.ringSize).toBe(512);
    expect(parsed.operations['http.POST./api/ibkr/order'].p95).toBe(82);
    expect(parsed.execution.distributions.broker_ack_ms.p99).toBe(78);
    expect(parsed.execution.segments.population.paper.sampleCount).toBe(20);
    expect(parsed.execution.segments.population.paper.sla?.status).toBe('pass');
    expect(
      parsed.execution.segments.fillProvenance.execDetails
        .exchangeToCallback.count,
    ).toBe(5);
    expect(parsed.execution.segments.fillLeg.target.aggregateEligibleCount).toBe(0);
    expect(parsed.execution.segments.fillLeg.target.slippageBps.count).toBe(1);
    expect(parsed.execution.excludedReasons.cross_boot).toBe(2);
  });

  it('preserves mixed aggregate suppression and population labels', () => {
    const parsed = parseLatencyDashboard(
      REPRESENTATIVE_OPERATIONS_PAYLOAD,
      REPRESENTATIVE_EXECUTION_PAYLOAD,
    );

    expect(
      parsed.execution.distributions.receive_to_complete_fill_ms.sufficient,
    ).toBe(false);
    expect(parsed.execution.aggregateScope).toBe('mixed_diagnostic_only');
    expect(parsed.execution.slaStatus).toBe('suppressed_mixed_population');
    expect(parsed.execution.slaPass).toBeNull();
    expect(parsed.execution.normalizedPopulations).toEqual([
      'benchmark_synthetic', 'live', 'paper',
    ]);
    expect(populationLabel('paper')).toBe('Paper');
    expect(populationLabel('live')).toBe('Live');
    expect(populationLabel('benchmark_synthetic')).toBe('Benchmark · synthetic');
  });

  it('marks only old dashboard fetches stale', () => {
    const parsed = parseLatencyDashboard(
      REPRESENTATIVE_OPERATIONS_PAYLOAD,
      REPRESENTATIVE_EXECUTION_PAYLOAD,
      100_000,
    );

    expect(isLatencySnapshotStale(parsed, 110_000)).toBe(false);
    expect(isLatencySnapshotStale(parsed, 120_000)).toBe(true);
  });

  it('fails closed to empty values for malformed numeric fields', () => {
    const parsed = parseLatencyDashboard(
      {
        operations: {
          unsafe: {
            count: -5,
            p95_ms: 'not-a-number',
            last_sample_age_ms: Number.POSITIVE_INFINITY,
          },
        },
      },
      { segments: null, distributions: [] },
    );

    expect(parsed.operations.unsafe.count).toBe(0);
    expect(parsed.operations.unsafe.p95).toBeNull();
    expect(parsed.operations.unsafe.lastSampleAgeMs).toBeNull();
    expect(parsed.execution.sampleCount).toBe(0);
  });
});
