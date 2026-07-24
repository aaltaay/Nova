import {
  LATENCY_DATA_STALE_MS,
  LATENCY_MAX_OPERATION_ROWS,
  LATENCY_MAX_SEGMENT_ROWS,
} from './constants';
import type {
  DistributionMetric,
  ExecutionLatencySnapshot,
  ExecutionSegmentSummary,
  FillLegSummary,
  FillProvenanceSummary,
  LatencyDashboardSnapshot,
  OperationMetric,
} from './types';

type JsonRecord = Record<string, unknown>;

function record(value: unknown): JsonRecord {
  return value != null && typeof value === 'object' && !Array.isArray(value)
    ? value as JsonRecord
    : {};
}

function finite(value: unknown): number | null {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function count(value: unknown): number {
  return Math.max(0, Math.trunc(finite(value) ?? 0));
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function boundedEntries(value: unknown, limit: number): [string, unknown][] {
  return Object.entries(record(value)).slice(0, limit);
}

function countMap(value: unknown): Record<string, number> {
  return Object.fromEntries(
    boundedEntries(value, LATENCY_MAX_SEGMENT_ROWS)
      .map(([key, raw]) => [key.slice(0, 64), count(raw)]),
  );
}

export function parseDistribution(value: unknown): DistributionMetric {
  const raw = record(value);
  return {
    count: count(raw.count),
    errorCount: count(raw.error_count),
    p50: finite(raw.p50 ?? raw.p50_ms),
    p95: finite(raw.p95 ?? raw.p95_ms),
    p99: finite(raw.p99 ?? raw.p99_ms),
    max: finite(raw.max ?? raw.max_ms),
    sufficient:
      typeof raw.sufficient === 'boolean' ? raw.sufficient : null,
    minimumSamples: finite(raw.minimum_samples),
    excludedCount: count(raw.excluded_count),
    excludedReasons: countMap(raw.excluded_reasons),
  };
}

function parseDistributions(value: unknown): Record<string, DistributionMetric> {
  return Object.fromEntries(
    boundedEntries(value, LATENCY_MAX_SEGMENT_ROWS)
      .map(([name, raw]) => [name.slice(0, 64), parseDistribution(raw)]),
  );
}

function parseSegment(value: unknown): ExecutionSegmentSummary {
  const raw = record(value);
  const sla = record(raw.sla);
  return {
    sampleCount: count(raw.sample_count),
    errorCount: count(raw.error_count),
    distributions: parseDistributions(raw.distributions),
    sla: Object.keys(sla).length === 0 ? null : {
      targetP95Ms: finite(sla.target_p95_ms),
      p95Ms: finite(sla.p95_ms),
      pass: typeof sla.pass === 'boolean' ? sla.pass : null,
      status: text(sla.status),
      evidenceSufficient: sla.evidence_sufficient === true,
    },
  };
}

function parseSegmentGroup(value: unknown): Record<string, ExecutionSegmentSummary> {
  return Object.fromEntries(
    boundedEntries(value, LATENCY_MAX_SEGMENT_ROWS)
      .map(([name, raw]) => [name.slice(0, 64), parseSegment(raw)]),
  );
}

function parseProvenance(value: unknown): Record<string, FillProvenanceSummary> {
  return Object.fromEntries(
    boundedEntries(value, LATENCY_MAX_SEGMENT_ROWS).map(([name, value]) => {
      const raw = record(value);
      return [
        name.slice(0, 64),
        {
          callbackFromSend: parseDistribution(raw.callback_from_send_ms),
          exchangeToCallback: parseDistribution(raw.exchange_to_callback_ms),
          exchangeClockNote: text(raw.exchange_clock_note),
        },
      ];
    }),
  );
}

function parseFillLeg(value: unknown): Record<string, FillLegSummary> {
  return Object.fromEntries(
    boundedEntries(value, LATENCY_MAX_SEGMENT_ROWS).map(([name, value]) => {
      const raw = record(value);
      return [
        name.slice(0, 32),
        {
          evidenceCount: count(raw.evidence_count),
          aggregateEligibleCount: count(raw.aggregate_eligible_count),
          callbackFromSend: parseDistribution(raw.callback_from_send_ms),
          slippageBps: parseDistribution(raw.slippage_bps),
        },
      ];
    }),
  );
}

export function parseExecutionLatency(value: unknown): ExecutionLatencySnapshot {
  const raw = record(value);
  const segments = record(raw.segments);
  return {
    boundedLimit: count(raw.bounded_limit),
    populationCount: count(raw.population_count),
    sampleCount: count(raw.sample_count),
    ackCount: count(raw.ack_count),
    errorCount: count(raw.error_count),
    excludedCount: count(raw.excluded_count),
    excludedReasons: countMap(raw.excluded_reasons),
    normalizedPopulations: Array.isArray(raw.normalized_populations)
      ? raw.normalized_populations
        .slice(0, LATENCY_MAX_SEGMENT_ROWS)
        .map(item => text(item).slice(0, 64))
        .filter(Boolean)
      : [],
    mixedPopulation: raw.mixed_population === true,
    aggregateScope: text(raw.aggregate_scope),
    aggregateWarning: text(raw.aggregate_warning) || null,
    slaStatus: text(raw.sla_status),
    slaPass: typeof raw.sla_pass === 'boolean' ? raw.sla_pass : null,
    clockContract: Object.fromEntries(
      boundedEntries(raw.clock_contract, 12)
        .map(([key, item]) => [key.slice(0, 64), text(item)]),
    ),
    distributions: parseDistributions(raw.distributions),
    segments: {
      population: parseSegmentGroup(segments.population),
      mode: parseSegmentGroup(segments.mode),
      operation: parseSegmentGroup(segments.operation),
      source: parseSegmentGroup(segments.source),
      fillProvenance: parseProvenance(segments.fill_provenance),
      fillLeg: parseFillLeg(segments.fill_leg),
    },
  };
}

function parseOperation(value: unknown): OperationMetric {
  const raw = record(value);
  return {
    count: count(raw.count),
    errorCount: count(raw.error_count),
    sampleCount: count(raw.sample_count),
    p50: finite(raw.p50_ms),
    p95: finite(raw.p95_ms),
    p99: finite(raw.p99_ms),
    max: finite(raw.max_ms),
    lastSampleAgeMs: finite(raw.last_sample_age_ms),
  };
}

export function parseLatencyDashboard(
  operationsPayload: unknown,
  executionPayload: unknown,
  fetchedAtWallMs = Date.now(),
): LatencyDashboardSnapshot {
  const operations = record(operationsPayload);
  const dedicatedExecution = Object.keys(record(executionPayload)).length > 0
    ? executionPayload
    : operations.execution;
  return {
    fetchedAtWallMs,
    ringSize: count(operations.ring_size),
    operationClock: text(operations.clock),
    operations: Object.fromEntries(
      boundedEntries(operations.operations, LATENCY_MAX_OPERATION_ROWS)
        .map(([name, raw]) => [name.slice(0, 96), parseOperation(raw)]),
    ),
    execution: parseExecutionLatency(dedicatedExecution),
  };
}

export function isLatencySnapshotStale(
  snapshot: LatencyDashboardSnapshot,
  nowWallMs = Date.now(),
): boolean {
  return nowWallMs - snapshot.fetchedAtWallMs > LATENCY_DATA_STALE_MS;
}

export function populationLabel(value: string): string {
  if (value === 'paper') return 'Paper';
  if (value === 'live') return 'Live';
  if (value === 'benchmark_synthetic') return 'Benchmark · synthetic';
  if (value === 'benchmark_paper') return 'Benchmark · paper';
  return value.replaceAll('_', ' ') || 'Unknown';
}
