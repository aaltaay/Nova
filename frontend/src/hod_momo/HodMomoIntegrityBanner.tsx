import { useEffect, useState } from 'react';
import { API_BASE_URL, HOD_MOMO_INTEGRITY_POLL_MS } from '../constants';

const API = `${API_BASE_URL}/api`;

type IntegrityStatus = 'pass' | 'warn' | 'fail' | 'error';

interface IntegrityCheck {
  id: string;
  status: string;
  detail: string;
}

interface IntegrityReport {
  status?: IntegrityStatus | string;
  ok?: boolean;
  checks?: IntegrityCheck[];
  parts?: Record<string, string>;
  hod?: { metrics?: Record<string, unknown> };
}

export function HodMomoIntegrityBanner() {
  const [report, setReport] = useState<IntegrityReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const resp = await fetch(`${API}/integrity`);
        if (!resp.ok) {
          throw new Error(`HTTP ${resp.status}`);
        }
        const data = (await resp.json()) as IntegrityReport;
        if (!cancelled) {
          setReport(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      }
    }

    poll();
    const id = window.setInterval(poll, HOD_MOMO_INTEGRITY_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const status: IntegrityStatus = error
    ? 'error'
    : ((report?.status as IntegrityStatus) || 'pass');

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
            Check the header flag (API_DOWN / API_WEDGED) and click Start API if shown.
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
