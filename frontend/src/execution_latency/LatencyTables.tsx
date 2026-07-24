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

export function OperationMetricsTable({
  operations,
}: {
  operations: Record<string, OperationMetric>;
}) {
  const rows = Object.entries(operations);
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
                <th>Operation</th><th>p50</th><th>p95</th><th>p99</th>
                <th>Max</th><th>Samples</th><th>Errors</th><th>Age</th>
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
  const rows = Object.entries(execution.distributions);
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
                <th>Hop</th><th>p50</th><th>p95</th><th>p99</th>
                <th>Max</th><th>Count</th><th>Errors</th><th>Evidence</th>
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

export function SegmentTable({
  title,
  segments,
  population = false,
}: {
  title: string;
  segments: Record<string, ExecutionSegmentSummary>;
  population?: boolean;
}) {
  const rows = Object.entries(segments);
  return (
    <section className="latency-card">
      <h3>{title}</h3>
      {rows.length === 0 ? (
        <p className="latency-empty">No segments in the bounded execution window.</p>
      ) : (
        <table className="latency-table">
          <thead>
            <tr>
              <th>Segment</th><th>Ack p50</th><th>Ack p95</th>
              <th>Samples</th><th>Errors</th>
              {population && <th>Population SLA</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map(([name, summary]) => {
              const metric = segmentMetric(summary);
              return (
                <tr key={name}>
                  <td>
                    <span className={`latency-population latency-population--${name}`}>
                      {population ? populationLabel(name) : name.replaceAll('_', ' ')}
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
              <tr><th>Action</th><th>Boundary</th><th>Action → request</th><th>Request → response</th><th>Response → visible</th><th>Result</th></tr>
            </thead>
            <tbody>
              {samples.map((item, index) => (
                <tr key={`${item.observedWallMs}-${item.operation}-${index}`}>
                  <td>{item.operation.replaceAll('_', ' ')}</td>
                  <td>{item.actionSource === 'user_action' ? 'User action' : 'Client call'}</td>
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
