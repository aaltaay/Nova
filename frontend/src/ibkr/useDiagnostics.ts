/**
 * Poll `GET /api/diagnostics` (ADR 021) while the checklist is open. Reports
 * the UI's own release tag so the API can say whether they match. An API that
 * cannot answer is an error the gate shows -- never an invented checklist.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { DIAG_BUNDLE_PATH, DIAG_PATH, DIAG_POLL_MS } from '../constantGroups/diagnostics';
import type { DiagnosticsPayload } from './diagnosticsTypes';

function uiTag(): string {
  return typeof __NOVA_RELEASE_TAG__ === 'string' ? __NOVA_RELEASE_TAG__ : '';
}

export function diagnosticsUrl(path: string = DIAG_PATH): string {
  const tag = uiTag();
  return `${API_BASE_URL}${path}${tag ? `?ui=${encodeURIComponent(tag)}` : ''}`;
}

export interface DiagnosticsState {
  data: DiagnosticsPayload | null;
  error: string | null;
  loading: boolean;
  refresh: () => void;
}

export function useDiagnostics(enabled: boolean): DiagnosticsState {
  const [data, setData] = useState<DiagnosticsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const alive = useRef(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await novaFetch(diagnosticsUrl(), { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = (await res.json()) as DiagnosticsPayload;
      if (!alive.current) return;
      if (!body || !Array.isArray(body.rows)) throw new Error('unexpected diagnostics payload');
      setData(body);
      setError(null);
    } catch (err) {
      if (!alive.current) return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (alive.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  useEffect(() => {
    if (!enabled) return undefined;
    void load();
    const id = window.setInterval(() => void load(), DIAG_POLL_MS);
    return () => window.clearInterval(id);
  }, [enabled, load]);

  return { data, error, loading, refresh: () => void load() };
}

/** The same checklist as plain text, for the Copy button. */
export async function fetchDiagnosticsBundle(): Promise<string> {
  const res = await novaFetch(diagnosticsUrl(DIAG_BUNDLE_PATH), { cache: 'no-store' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.text();
}
