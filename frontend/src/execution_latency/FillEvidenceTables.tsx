import type { ExecutionLatencySnapshot } from './types';

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

export function FillEvidenceTables({
  execution,
}: {
  execution: ExecutionLatencySnapshot;
}) {
  const provenance = Object.entries(execution.segments.fillProvenance);
  const legs = Object.entries(execution.segments.fillLeg);
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
              <th>Source</th><th>Send → callback p95</th>
              <th>Exchange → callback p95</th><th>Samples</th><th>Excluded</th>
            </tr>
          </thead>
          <tbody>
            {provenance.map(([name, item]) => (
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
        {legs.length === 0 ? (
          <p className="latency-empty">No leg-attributed fill evidence.</p>
        ) : (
          <table className="latency-table">
            <thead>
              <tr>
                <th>Leg</th><th>Eligibility</th><th>Callback p95</th>
                <th>Slippage p50</th><th>Slippage p95</th><th>Unavailable</th>
              </tr>
            </thead>
            <tbody>
              {legs.map(([role, item]) => {
                const childExcluded = item.aggregateEligibleCount === 0;
                const unavailable = Math.max(
                  0,
                  item.evidenceCount - item.slippageBps.count,
                );
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
