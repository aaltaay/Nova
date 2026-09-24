import { useMemo } from 'react';
import { SortTh, useTableSort, type SortColumns } from '../table_sort';
import { LATENCY_DATA_STALE_MS } from './constants';
import { populationLabel } from './model';
import type {
  BrowserTimingSample,
  DistributionMetric,
  ExecutionLatencySnapshot,
  ExecutionSegmentSummary,
  OperationMetric,
} from './types';

function ms(value: number | null): string {
  return value == null ? '—' : `${value.toFixed(value >= 100 ? 0 : 1)} ms`;
}

function age(value: number | null): string {
  if (value == null) return '—';
  if (value < 1_000) return `${Math.round(value)} ms`;
  return `${(value / 1_000).toFixed(value < 10_000 ? 1 : 0)} s`;
}

function metricName(value: string): string {
  const labels: Record<string, string> = {
    validation_ms: 'Ingress → validation',
    persistence_ms: 'Ingress → persisted',
    broker_send_ms: 'Ingress → broker send',
    broker_ack_ms: 'Ingress → broker ack',
    receive_to_first_fill_ms: 'Ingress → first fill',
    send_to_first_fill_ms: 'Broker send → first fill',
    ack_to_first_fill_ms: 'Broker ack → first fill',
    receive_to_complete_fill_ms: 'Ingress → complete fill',
    send_to_complete_fill_ms: 'Broker send → complete fill',
    ack_to_complete_fill_ms: 'Broker ack → complete fill',
    backend_response_ready_ms: 'Ingress → handler response-ready',
  };
  return labels[value] ?? value.replaceAll('_', ' ');
}

function sampleWarning(metric: DistributionMetric): string {
  if (metric.sufficient === false) {
    return `Insufficient (${metric.count}/${metric.minimumSamples ?? '?'})`;
  }
  return metric.sufficient === true ? 'Sufficient' : 'Not labeled';
}

function boundaryLabel(sample: BrowserTimingSample): string {
  return sample.actionSource === 'user_action' ? 'User action' : 'Client call';
}

type OperationRow = [string, OperationMetric];
type HopRow = [string, DistributionMetric];
type SegmentRow = [string, ExecutionSegmentSummary];

const OPERATION_COLUMNS: SortColumns<OperationRow> = {
  operation: ([name]) => name,
  p50: ([, m]) => m.p50,
  p95: ([, m]) => m.p95,
  p99: ([, m]) => m.p99,
  max: ([, m]) => m.max,
  // Every operation seen, not the retained ring (which caps at its size).
  samples: ([, m]) => m.count,
  errors: ([, m]) => m.errorCount,
  age: ([, m]) => m.lastSampleAgeMs,
};

const HOP_COLUMNS: SortColumns<HopRow> = {
  hop: ([name]) => metricName(name),
  p50: ([, m]) => m.p50,
  p95: ([, m]) => m.p95,
  p99: ([, m]) => m.p99,
  max: ([, m]) => m.max,
  count: ([, m]) => m.count,
  errors: ([, m]) => m.errorCount,
  // Sufficient first; an unlabeled distribution is unknown.
  evidence: ([, m]) => m.sufficient,
};

const BROWSER_COLUMNS: SortColumns<BrowserTimingSample> = {
  action: s => s.operation.replaceAll('_', ' '),
  boundary: s => boundaryLabel(s),
  toRequest: s => s.actionToRequestMs,
  toResponse: s => s.requestToResponseMs,
  toVisible: s => s.responseToVisibleMs,
  result: s => s.outcome,
};

export function OperationMetricsTable({
  operations,
}: {
  operations: Record<string, OperationMetric>;
}) {
  const { rows, sort, onSort } = useTableSort(
    'execution_latency.operations',
    Object.entries(operations),
    OPERATION_COLUMNS,
  );
  return (
    <section className="latency-card">
      <h3>Process-local operation metrics</h3>
      <p className="latency-help">
        Bounded in-memory rings. Counts can exceed retained samples; rings reset on API restart.
      </p>
      {rows.length === 0 ? (
        <p className="latency-empty">No operation samples recorded in this process.</p>
      ) : (
        <div className="latency-table-scroll">
          <table className="latency-table">
            <thead>
              <tr>
                <SortTh col="operation" sort={sort} onSort={onSort}>Operation</SortTh>
                <SortTh col="p50" sort={sort} onSort={onSort}>p50</SortTh>
                <SortTh col="p95" sort={sort} onSort={onSort}>p95</SortTh>
                <SortTh col="p99" sort={sort} onSort={onSort}>p99</SortTh>
                <SortTh col="max" sort={sort} onSort={onSort}>Max</SortTh>
                <SortTh col="samples" sort={sort} onSort={onSort}>Samples</SortTh>
                <SortTh col="errors" sort={sort} onSort={onSort}>Errors</SortTh>
                <SortTh col="age" sort={sort} onSort={onSort}>Age</SortTh>
              </tr>
            </thead>
            <tbody>
              {rows.map(([name, item]) => (
                <tr key={name}>
                  <td><code>{name}</code></td>
                  <td>{ms(item.p50)}</td><td>{ms(item.p95)}</td>
                  <td>{ms(item.p99)}</td><td>{ms(item.max)}</td>
                  <td>{item.sampleCount}/{item.count}</td>
                  <td>{item.errorCount}</td>
                  <td className={
                    item.lastSampleAgeMs != null
                    && item.lastSampleAgeMs > LATENCY_DATA_STALE_MS
                      ? 'latency-warn'
                      : ''
                  }>
                    {age(item.lastSampleAgeMs)}
                    {item.lastSampleAgeMs != null
                    && item.lastSampleAgeMs > LATENCY_DATA_STALE_MS
                      ? ' · stale'
                      : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function ExecutionHopTable({
  execution,
}: {
  execution: ExecutionLatencySnapshot;
}) {
  const { rows, sort, onSort } = useTableSort(
    'execution_latency.hops',
    Object.entries(execution.distributions),
    HOP_COLUMNS,
  );
  return (
    <section className="latency-card">
      <h3>Backend hops and fill stages</h3>
      <p className="latency-help">
        Backend-only same-boot monotonic deltas. First fill and complete fill are separate.
      </p>
      {rows.length === 0 ? (
        <p className="latency-empty">No same-boot execution distributions available.</p>
      ) : (
        <div className="latency-table-scroll">
          <table className="latency-table">
            <thead>
              <tr>
                <SortTh col="hop" sort={sort} onSort={onSort}>Hop</SortTh>
                <SortTh col="p50" sort={sort} onSort={onSort}>p50</SortTh>
                <SortTh col="p95" sort={sort} onSort={onSort}>p95</SortTh>
                <SortTh col="p99" sort={sort} onSort={onSort}>p99</SortTh>
                <SortTh col="max" sort={sort} onSort={onSort}>Max</SortTh>
                <SortTh col="count" sort={sort} onSort={onSort}>Count</SortTh>
                <SortTh col="errors" sort={sort} onSort={onSort}>Errors</SortTh>
                <SortTh col="evidence" sort={sort} onSort={onSort}>Evidence</SortTh>
              </tr>
            </thead>
            <tbody>
              {rows.map(([name, item]) => (
                <tr key={name}>
                  <td>{metricName(name)}</td>
                  <td>{ms(item.p50)}</td><td>{ms(item.p95)}</td>
                  <td>{ms(item.p99)}</td><td>{ms(item.max)}</td>
                  <td>{item.count}</td><td>{item.errorCount}</td>
                  <td>
                    <span className={item.sufficient === false ? 'latency-warn' : ''}>
                      {sampleWarning(item)}
                    </span>
                    {item.excludedCount > 0 && ` · ${item.excludedCount} excluded`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function segmentMetric(summary: ExecutionSegmentSummary): DistributionMetric {
  return summary.distributions.broker_ack_ms ?? {
    count: 0, errorCount: summary.errorCount, p50: null, p95: null,
    p99: null, max: null, sufficient: null, minimumSamples: null,
    excludedCount: 0, excludedReasons: {},
  };
}

function segmentLabel(name: string, population: boolean): string {
  return population ? populationLabel(name) : name.replaceAll('_', ' ');
}

/** The population SLA as a sort value: pass above fail; no verdict is unknown. */
function slaPassed(summary: ExecutionSegmentSummary): boolean | null {
  const status = summary.sla?.status;
  return status === 'pass' ? true : status === 'fail' ? false : null;
}

export function SegmentTable({
  title,
  segments,
  population = false,
}: {
  title: string;
  segments: Record<string, ExecutionSegmentSummary>;
  population?: boolean;
}) {
  const columns = useMemo<SortColumns<SegmentRow>>(() => ({
    segment: ([name]) => segmentLabel(name, population),
    ackP50: ([, summary]) => segmentMetric(summary).p50,
    ackP95: ([, summary]) => segmentMetric(summary).p95,
    samples: ([, summary]) => segmentMetric(summary).count,
    errors: ([, summary]) => summary.errorCount,
    sla: ([, summary]) => slaPassed(summary),
  }), [population]);
  // One remembered sort per segment table: the dashboard shows four.
  const tableId = `execution_latency.segments.${title.toLowerCase().replaceAll(' ', '_')}`;
  const { rows, sort, onSort } = useTableSort(tableId, Object.entries(segments), columns);
  return (
    <section className="latency-card">
      <h3>{title}</h3>
      {rows.length === 0 ? (
        <p className="latency-empty">No segments in the bounded execution window.</p>
      ) : (
        <table className="latency-table">
          <thead>
            <tr>
              <SortTh col="segment" sort={sort} onSort={onSort}>Segment</SortTh>
              <SortTh col="ackP50" sort={sort} onSort={onSort}>Ack p50</SortTh>
              <SortTh col="ackP95" sort={sort} onSort={onSort}>Ack p95</SortTh>
              <SortTh col="samples" sort={sort} onSort={onSort}>Samples</SortTh>
              <SortTh col="errors" sort={sort} onSort={onSort}>Errors</SortTh>
              {population && <SortTh col="sla" sort={sort} onSort={onSort}>Population SLA</SortTh>}
            </tr>
          </thead>
          <tbody>
            {rows.map(([name, summary]) => {
              const metric = segmentMetric(summary);
              return (
                <tr key={name}>
                  <td>
                    <span className={`latency-population latency-population--${name}`}>
                      {segmentLabel(name, population)}
                    </span>
                  </td>
                  <td>{ms(metric.p50)}</td><td>{ms(metric.p95)}</td>
                  <td className={metric.sufficient === false ? 'latency-warn' : ''}>
                    {metric.count}
                  </td>
                  <td>{summary.errorCount}</td>
                  {population && (
                    <td className={
                      summary.sla?.status === 'fail'
                        ? 'latency-error'
                        : summary.sla?.status === 'pass'
                          ? 'latency-ok'
                          : 'latency-warn'
                    }>
                      {summary.sla?.status === 'pass'
                        ? 'Pass'
                        : summary.sla?.status === 'fail'
                          ? 'Fail'
                          : 'Insufficient samples'}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}

export function BrowserTimingTable({
  samples,
}: {
  samples: readonly BrowserTimingSample[];
}) {
  const { rows, sort, onSort } = useTableSort('execution_latency.browser_timing', samples, BROWSER_COLUMNS);
  return (
    <section className="latency-card">
      <h3>Browser-local action timing</h3>
      <p className="latency-help">
        Same-document performance.now() only. “Visible” means the second animation frame after response.
      </p>
      {samples.length === 0 ? (
        <p className="latency-empty">No instrumented trading action in this browser session.</p>
      ) : (
        <div className="latency-table-scroll">
          <table className="latency-table">
            <thead>
              <tr>
                <SortTh col="action" sort={sort} onSort={onSort}>Action</SortTh>
                <SortTh col="boundary" sort={sort} onSort={onSort}>Boundary</SortTh>
                <SortTh col="toRequest" sort={sort} onSort={onSort}>Action → request</SortTh>
                <SortTh col="toResponse" sort={sort} onSort={onSort}>Request → response</SortTh>
                <SortTh col="toVisible" sort={sort} onSort={onSort}>Response → visible</SortTh>
                <SortTh col="result" sort={sort} onSort={onSort}>Result</SortTh>
              </tr>
            </thead>
            <tbody>
              {rows.map((item, index) => (
                <tr key={`${item.observedWallMs}-${item.operation}-${index}`}>
                  <td>{item.operation.replaceAll('_', ' ')}</td>
                  <td>{boundaryLabel(item)}</td>
                  <td>{ms(item.actionToRequestMs)}</td>
                  <td>{ms(item.requestToResponseMs)}</td>
                  <td>{ms(item.responseToVisibleMs)}</td>
                  <td className={item.outcome === 'ok' ? 'latency-ok' : 'latency-error'}>
                    {item.outcome}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
