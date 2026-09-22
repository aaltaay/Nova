import { useHodMomoIntegrity, type IntegrityStatus } from './useHodMomoIntegrity';

export function HodMomoIntegrityBanner() {
  const { report, error, status: polled } = useHodMomoIntegrity();
  const status: IntegrityStatus = polled === 'loading' ? 'pass' : polled;

  if (status === 'pass' && !error) {
    return null;
  }

  const failed = (report?.checks || []).filter(c => c.status !== 'pass');
  const metrics = report?.hod?.metrics || {};
  const uncovered = Array.isArray(metrics.uncovered_symbols)
    ? (metrics.uncovered_symbols as string[]).slice(0, 8)
    : [];

  return (
    <div
      className={`hod-integrity hod-integrity-${status}`}
      role="status"
      aria-live="polite"
      data-testid="hod-integrity-banner"
      data-status={status}
    >
      <strong>
        {status === 'error' ? 'Integrity unreachable' : `Integrity ${status}`}
      </strong>
      {error ? (
        <div>
          {error}
          <div className="hod-integrity-hint">
            Check the header flag. Start API only for API_DOWN -- never auto-kill on WEDGED.
          </div>
        </div>
      ) : (
        <>
          {failed.length > 0 && (
            <ul className="hod-integrity-list">
              {failed.slice(0, 6).map(c => (
                <li key={c.id}>
                  <span className="hod-integrity-id">{c.id}</span>: {c.detail}
                </li>
              ))}
            </ul>
          )}
          {uncovered.length > 0 && (
            <div>
              Uncovered (watched, not live): {uncovered.join(', ')}
              {Number(metrics.uncovered_count || 0) > uncovered.length ? '…' : ''}
            </div>
          )}
        </>
      )}
    </div>
  );
}
