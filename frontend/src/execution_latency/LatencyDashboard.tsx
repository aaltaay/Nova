import {
  BACKEND_TIMING_CLOCK_LABEL,
  BROWSER_TIMING_CLOCK_LABEL,
  WALL_CLOCK_LIMITATION,
} from './constants';
import { FillEvidenceTables } from './FillEvidenceTables';
import {
  BrowserTimingTable,
  ExecutionHopTable,
  OperationMetricsTable,
  SegmentTable,
} from './LatencyTables';
import { isLatencySnapshotStale } from './model';
import type {
  BrowserTimingSample,
  LatencyDashboardSnapshot,
} from './types';
import { useBrowserTimingSamples } from './useBrowserTimingSamples';
import { useLatencyMetrics } from './useLatencyMetrics';
import './latencyDashboard.css';

interface ViewProps {
  snapshot: LatencyDashboardSnapshot | null;
  browserSamples: readonly BrowserTimingSample[];
  loading: boolean;
  error: string | null;
  onRefresh?: () => void;
  nowWallMs?: number;
}

function SummaryCard({
  label,
  value,
  detail,
  tone = '',
}: {
  label: string;
  value: string | number;
  detail: string;
  tone?: string;
}) {
  return (
    <article className={`latency-summary-card ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function ExclusionList({
  reasons,
}: {
  reasons: Record<string, number>;
}) {
  const rows = Object.entries(reasons);
  if (rows.length === 0) return <span>None in the bounded window</span>;
  return (
    <ul className="latency-exclusions">
      {rows.map(([reason, count]) => (
        <li key={reason}>
          <code>{reason}</code>: {count}
        </li>
      ))}
    </ul>
  );
}

export function LatencyDashboardView({
  snapshot,
  browserSamples,
  loading,
  error,
  onRefresh,
  nowWallMs = Date.now(),
}: ViewProps) {
  const stale = snapshot ? isLatencySnapshotStale(snapshot, nowWallMs) : false;
  const execution = snapshot?.execution ?? null;
  const noData = snapshot != null
    && Object.keys(snapshot.operations).length === 0
    && execution?.populationCount === 0;

  return (
    <div className="latency-dashboard" data-testid="latency-dashboard">
      <header className="latency-header">
        <div>
          <p className="latency-kicker">ADR 007 · read-only evidence</p>
          <h2>Execution Latency</h2>
          <p>
            Aggregate operation, broker acknowledgment, fill, and browser-visible timing.
            This page never sends an order or starts a probe.
          </p>
        </div>
        <button type="button" className="ibkr-btn-secondary" onClick={onRefresh}>
          Refresh
        </button>
      </header>

      {loading && !snapshot && (
        <div className="latency-state" role="status">Loading bounded latency metrics…</div>
      )}
      {error && (
        <div className="latency-state latency-state--error" role="alert">{error}</div>
      )}
      {stale && (
        <div className="latency-state latency-state--warn" role="status">
          Stale dashboard fetch — the API has not refreshed this view within the expected window.
        </div>
      )}
      {noData && (
        <div className="latency-state" role="status">
          Empty evidence window. No production claim can be made until samples exist.
        </div>
      )}

      {snapshot && execution && (
        <>
          <section className="latency-summary" aria-label="Execution latency summary">
            <SummaryCard
              label="Execution samples"
              value={execution.sampleCount}
              detail={`${execution.populationCount} rows read · cap ${execution.boundedLimit}`}
            />
            <SummaryCard
              label="Broker acknowledgments"
              value={execution.ackCount}
              detail={
                execution.mixedPopulation
                  ? 'Mixed aggregate · diagnostic only'
                  : execution.distributions.broker_ack_ms?.sufficient
                  ? 'Percentile sample threshold met'
                  : 'Insufficient percentile evidence'
              }
              tone={
                !execution.mixedPopulation
                && execution.distributions.broker_ack_ms?.sufficient
                  ? ''
                  : 'is-warning'
              }
            />
            <SummaryCard
              label="Aggregate SLA"
              value={
                execution.slaStatus === 'suppressed_mixed_population'
                  ? 'Suppressed'
                  : execution.slaPass === true
                    ? 'Pass'
                    : execution.slaPass === false
                      ? 'Fail'
                      : 'Insufficient'
              }
              detail={
                execution.mixedPopulation
                  ? 'Verdicts live on population rows'
                  : 'Single normalized population only'
              }
              tone={
                execution.slaPass === false
                  ? 'is-danger'
                  : execution.slaPass === true
                    ? ''
                    : 'is-warning'
              }
            />
            <SummaryCard
              label="Errors"
              value={execution.errorCount}
              detail="Rejected and failed executions"
              tone={execution.errorCount > 0 ? 'is-danger' : ''}
            />
            <SummaryCard
              label="Excluded"
              value={execution.excludedCount}
              detail="Legacy, cross-boot, negative, or unsent rows"
              tone={execution.excludedCount > 0 ? 'is-warning' : ''}
            />
          </section>

          <section className="latency-honesty" aria-label="Measurement limitations">
            <h3>Measurement contract</h3>
            <ul>
              <li><strong>Browser:</strong> {BROWSER_TIMING_CLOCK_LABEL}.</li>
              <li><strong>Backend:</strong> {BACKEND_TIMING_CLOCK_LABEL}.</li>
              <li><strong>Cross-clock:</strong> browser and backend monotonic values are never subtracted.</li>
              <li><strong>Wall clocks:</strong> {WALL_CLOCK_LIMITATION}</li>
              <li><strong>Populations:</strong> paper, live, benchmark, operation, and source stay separate.</li>
              <li><strong>Lifecycle:</strong> operation rings and browser samples reset on restart/reload.</li>
              <li><strong>Slippage:</strong> side-aware fill-leg aggregates are shown; child legs remain excluded from parent SLA.</li>
            </ul>
          </section>

          {execution.mixedPopulation && (
            <div className="latency-state latency-state--warn" role="status">
              {execution.aggregateWarning
                ?? 'Mixed execution populations are diagnostic only.'}
              {' '}Populations: {execution.normalizedPopulations.join(', ') || 'unknown'}.
              Use population SLA rows; the aggregate has no verdict.
            </div>
          )}

          <OperationMetricsTable operations={snapshot.operations} />
          <BrowserTimingTable samples={browserSamples} />
          <ExecutionHopTable execution={execution} />

          <div className="latency-grid">
            <SegmentTable
              title="Population"
              segments={execution.segments.population}
              population
            />
            <SegmentTable title="Account mode" segments={execution.segments.mode} />
            <SegmentTable title="Operation" segments={execution.segments.operation} />
            <SegmentTable title="Source" segments={execution.segments.source} />
          </div>

          <FillEvidenceTables execution={execution} />

          <section className="latency-card">
            <h3>Excluded evidence</h3>
            <p className="latency-help">
              Exclusions remain counted rather than silently entering a distribution.
            </p>
            <ExclusionList reasons={execution.excludedReasons} />
          </section>
        </>
      )}
    </div>
  );
}

export function LatencyDashboard() {
  const metrics = useLatencyMetrics();
  const browserSamples = useBrowserTimingSamples();
  return (
    <LatencyDashboardView
      snapshot={metrics.snapshot}
      browserSamples={browserSamples}
      loading={metrics.loading}
      error={metrics.error}
      onRefresh={metrics.refresh}
    />
  );
}
