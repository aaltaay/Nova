/**
 * One poll of /api/integrity shared by the strip's dot and the legacy banner.
 * Status words: pass | warn | fail | error (unreachable) | loading (no answer yet).
 */
import { useEffect, useState } from 'react';
import { API_BASE_URL, HOD_MOMO_INTEGRITY_POLL_MS } from '../constants';

export type IntegrityStatus = 'pass' | 'warn' | 'fail' | 'error';

export interface IntegrityCheck {
  id: string;
  status: string;
  detail: string;
}

export interface IntegrityReport {
  status?: IntegrityStatus | string;
  ok?: boolean;
  checks?: IntegrityCheck[];
  parts?: Record<string, string>;
  hod?: { metrics?: Record<string, unknown> };
}

export interface HodMomoIntegrityState {
  report: IntegrityReport | null;
  error: string | null;
  /** 'loading' until the first answer, then the report's status or 'error'. */
  status: IntegrityStatus | 'loading';
}

export function useHodMomoIntegrity(): HodMomoIntegrityState {
  const [report, setReport] = useState<IntegrityReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const resp = await fetch(`${API_BASE_URL}/api/integrity`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = (await resp.json()) as IntegrityReport;
        if (!cancelled) {
          setReport(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    }

    void poll();
    const id = window.setInterval(() => void poll(), HOD_MOMO_INTEGRITY_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const status: HodMomoIntegrityState['status'] = error
    ? 'error'
    : report
      ? ((report.status as IntegrityStatus) || 'pass')
      : 'loading';

  return { report, error, status };
}
