/**
 * The auto-record switch's one door: `POST /api/auto-record {mode}` (operator
 * ask 2026-10-14; `architecture/schema/scanner.md`, Auto-record). The status
 * poll is the truth afterwards -- the reply is never taken for it -- and a
 * refusal (`.env` holds it off, the file could not be written) is shown in words.
 */
import { useCallback, useState } from 'react';
import { novaFetch } from '../../api/novaFetch';
import { API_BASE_URL } from '../../constants';
import { refreshIbkrStatusNow } from '../../ibkr/ibkrStatusPoller';
import type { AutoRecordMode } from '../../ibkr/types';
import { capturesResource } from '../../sim/useSimSessionController';

/** Save the switch; the reason it did not change, or null. */
export async function postAutoRecordMode(mode: AutoRecordMode): Promise<string | null> {
  let error: string | null = null;
  try {
    const res = await novaFetch(`${API_BASE_URL}/api/auto-record`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null) as { detail?: unknown } | null;
      error = typeof body?.detail === 'string' ? body.detail : `Nova answered ${res.status || 'an error'}`;
    }
  } catch {
    error = 'Could not reach Nova';
  }
  refreshIbkrStatusNow();
  if (!error && mode !== 'on') void capturesResource.refresh();
  return error;
}

export interface AutoRecordSwitchControl {
  /** The mode being saved, while its request is in flight. */
  busy: AutoRecordMode | null;
  error: string | null;
  setMode: (mode: AutoRecordMode) => Promise<void>;
}

export function useAutoRecordSwitch(): AutoRecordSwitchControl {
  const [busy, setBusy] = useState<AutoRecordMode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const setMode = useCallback(async (mode: AutoRecordMode) => {
    setBusy(mode);
    setError(null);
    const failed = await postAutoRecordMode(mode);
    setError(failed);
    setBusy(null);
  }, []);
  return { busy, error, setMode };
}
