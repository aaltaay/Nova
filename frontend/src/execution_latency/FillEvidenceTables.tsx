import { SortTh, useTableSort, type SortColumns } from '../table_sort';
import type {
  ExecutionLatencySnapshot,
  FillLegSummary,
  FillProvenanceSummary,
} from './types';

function ms(value: number | null): string {
  return value == null ? '—' : `${value.toFixed(value >= 100 ? 0 : 1)} ms`;
}

function bps(value: number | null): string {
  return value == null ? '—' : `${value.toFixed(1)} bps`;
}

function legLabel(role: string): string {
  if (role === 'single') return 'Single order';
  if (role === 'parent') return 'Bracket parent';
  if (role === 'target') return 'Target child';
  if (role === 'stop') return 'Stop child';
  return role.replaceAll('_', ' ');
}

/** Fills with no slippage figure: missing evidence or excluded. */
function unavailableCount(item: FillLegSummary): number {
  return Math.max(0, item.evidenceCount - item.slippageBps.count);
}

type ProvenanceRow = [string, FillProvenanceSummary];
type LegRow = [string, FillLegSummary];

const PROVENANCE_COLUMNS: SortColumns<ProvenanceRow> = {
  source: ([name]) => name,
  sendP95: ([, item]) => item.callbackFromSend.p95,
  exchangeP95: ([, item]) => item.exchangeToCallback.p95,
  samples: ([, item]) => item.callbackFromSend.count,
  excluded: ([, item]) => item.callbackFromSend.excludedCount,
};

const LEG_COLUMNS: SortColumns<LegRow> = {
  leg: ([role]) => legLabel(role),
  // Aggregate-eligible fills; a child leg (0) sorts lowest.
  eligibility: ([, item]) => item.aggregateEligibleCount,
  callbackP95: ([, item]) => item.callbackFromSend.p95,
  slippageP50: ([, item]) => item.slippageBps.p50,
  slippageP95: ([, item]) => item.slippageBps.p95,
  unavailable: ([, item]) => unavailableCount(item),
};

export function FillEvidenceTables({
  execution,
}: {
  execution: ExecutionLatencySnapshot;
}) {
  const provenance = useTableSort(
    'execution_latency.fill_provenance',
    Object.entries(execution.segments.fillProvenance),
    PROVENANCE_COLUMNS,
  );
  const legs = useTableSort(
    'execution_latency.fill_legs',
    Object.entries(execution.segments.fillLeg),
    LEG_COLUMNS,
  );
  return (
    <div className="latency-grid">
      <section className="latency-card">
        <h3>Fill provenance</h3>
        <p className="latency-help">
          Callback receipt is not exchange time. Exchange → callback uses wall
          clocks and requires synchronization. Child legs do not enter the
          parent aggregate.
        </p>
        <table className="latency-table">
          <thead>
            <tr>
              <SortTh col="source" sort={provenance.sort} onSort={provenance.onSort}>Source</SortTh>
              <SortTh col="sendP95" sort={provenance.sort} onSort={provenance.onSort}>Send → callback p95</SortTh>
              <SortTh col="exchangeP95" sort={provenance.sort} onSort={provenance.onSort}>Exchange → callback p95</SortTh>
              <SortTh col="samples" sort={provenance.sort} onSort={provenance.onSort}>Samples</SortTh>
              <SortTh col="excluded" sort={provenance.sort} onSort={provenance.onSort}>Excluded</SortTh>
            </tr>
          </thead>
          <tbody>
            {provenance.rows.map(([name, item]) => (
              <tr key={name}>
                <td>{name}</td>
                <td>{ms(item.callbackFromSend.p95)}</td>
                <td title={item.exchangeClockNote}>
                  {ms(item.exchangeToCallback.p95)}
                </td>
                <td>{item.callbackFromSend.count}</td>
                <td className={item.callbackFromSend.excludedCount > 0 ? 'latency-warn' : ''}>
                  {item.callbackFromSend.excludedCount}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="latency-card">
        <h3>Fill legs and slippage</h3>
        <p className="latency-help">
          Slippage is side-aware. Child target/stop evidence is displayed but
          excluded from parent execution latency and SLA aggregates.
        </p>
        {legs.rows.length === 0 ? (
          <p className="latency-empty">No leg-attributed fill evidence.</p>
        ) : (
          <table className="latency-table">
            <thead>
              <tr>
                <SortTh col="leg" sort={legs.sort} onSort={legs.onSort}>Leg</SortTh>
                <SortTh col="eligibility" sort={legs.sort} onSort={legs.onSort}>Eligibility</SortTh>
                <SortTh col="callbackP95" sort={legs.sort} onSort={legs.onSort}>Callback p95</SortTh>
                <SortTh col="slippageP50" sort={legs.sort} onSort={legs.onSort}>Slippage p50</SortTh>
                <SortTh col="slippageP95" sort={legs.sort} onSort={legs.onSort}>Slippage p95</SortTh>
                <SortTh col="unavailable" sort={legs.sort} onSort={legs.onSort}>Unavailable</SortTh>
              </tr>
            </thead>
            <tbody>
              {legs.rows.map(([role, item]) => {
                const childExcluded = item.aggregateEligibleCount === 0;
                const unavailable = unavailableCount(item);
                return (
                  <tr key={role}>
                    <td>{legLabel(role)}</td>
                    <td className={childExcluded ? 'latency-warn' : 'latency-ok'}>
                      {childExcluded
                        ? 'Child leg · excluded'
                        : `${item.aggregateEligibleCount}/${item.evidenceCount} aggregate eligible`}
                    </td>
                    <td>{ms(item.callbackFromSend.p95)}</td>
                    <td>{bps(item.slippageBps.p50)}</td>
                    <td>{bps(item.slippageBps.p95)}</td>
                    <td className={unavailable > 0 ? 'latency-warn' : ''}>
                      {unavailable > 0
                        ? `${unavailable} missing/excluded`
                        : '0'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
