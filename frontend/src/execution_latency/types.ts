export interface ClientTimingPayload {
  action_wall_ms: number;
  action_performance_ms: number;
  request_wall_ms: number;
  request_performance_ms: number;
}

export type BrowserActionSource = 'user_action' | 'client_call';

export interface BrowserActionStamp {
  wallMs: number;
  performanceMs: number;
  source: BrowserActionSource;
}

export interface BrowserTimingSample {
  operation: string;
  actionSource: BrowserActionSource;
  outcome: 'ok' | 'error';
  observedWallMs: number;
  actionToRequestMs: number | null;
  requestToResponseMs: number | null;
  responseToVisibleMs: number | null;
  requestToVisibleMs: number | null;
  clockDomain: 'browser_performance_now_same_document';
}

export interface DistributionMetric {
  count: number;
  errorCount: number;
  p50: number | null;
  p95: number | null;
  p99: number | null;
  max: number | null;
  sufficient: boolean | null;
  minimumSamples: number | null;
  excludedCount: number;
  excludedReasons: Record<string, number>;
}

export interface ExecutionSegmentSummary {
  sampleCount: number;
  errorCount: number;
  distributions: Record<string, DistributionMetric>;
  sla: {
    targetP95Ms: number | null;
    p95Ms: number | null;
    pass: boolean | null;
    status: string;
    evidenceSufficient: boolean;
  } | null;
}

export interface FillProvenanceSummary {
  callbackFromSend: DistributionMetric;
  exchangeToCallback: DistributionMetric;
  exchangeClockNote: string;
}

export interface FillLegSummary {
  evidenceCount: number;
  aggregateEligibleCount: number;
  callbackFromSend: DistributionMetric;
  slippageBps: DistributionMetric;
}

export interface ExecutionLatencySnapshot {
  boundedLimit: number;
  populationCount: number;
  sampleCount: number;
  ackCount: number;
  errorCount: number;
  excludedCount: number;
  excludedReasons: Record<string, number>;
  normalizedPopulations: string[];
  mixedPopulation: boolean;
  aggregateScope: string;
  aggregateWarning: string | null;
  slaStatus: string;
  slaPass: boolean | null;
  clockContract: Record<string, string>;
  distributions: Record<string, DistributionMetric>;
  segments: {
    population: Record<string, ExecutionSegmentSummary>;
    mode: Record<string, ExecutionSegmentSummary>;
    operation: Record<string, ExecutionSegmentSummary>;
    source: Record<string, ExecutionSegmentSummary>;
    fillProvenance: Record<string, FillProvenanceSummary>;
    fillLeg: Record<string, FillLegSummary>;
  };
}

export interface OperationMetric {
  count: number;
  errorCount: number;
  sampleCount: number;
  p50: number | null;
  p95: number | null;
  p99: number | null;
  max: number | null;
  lastSampleAgeMs: number | null;
}

export interface LatencyDashboardSnapshot {
  fetchedAtWallMs: number;
  ringSize: number;
  operationClock: string;
  operations: Record<string, OperationMetric>;
  execution: ExecutionLatencySnapshot;
}
