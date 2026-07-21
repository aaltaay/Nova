import { useEffect, useState } from 'react';
import { API_BASE_URL } from '../constants';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import type { IbkrStatus } from './types';

const DEFAULT: IbkrStatus = {
  enabled: false,
  connected: false,
  mode: 'disconnected',
  orders_enabled: false,
  spend_status: 'locked',
};

const SAMPLE_STATUS: IbkrStatus = {
  enabled: true,
  connected: true,
  mode: 'paper',
  orders_enabled: false,
  spend_status: 'locked',
};

/** Broadcast to make every mounted useIbkrStatus() poll immediately (e.g. right
 * after a user-initiated Paper<->Live gateway-mode switch), without waiting
 * up to 5 s for the next interval tick. */
const REFRESH_EVENT = 'ibkr-status-refresh';

export function refreshIbkrStatusNow(): void {
  window.dispatchEvent(new Event(REFRESH_EVENT));
}

/** Polls /api/ibkr/status every 5 s to reflect IB Gateway connection state. */
export function useIbkrStatus(): IbkrStatus {
  const sample = useSampleDataOptional();
  const [status, setStatus] = useState<IbkrStatus>(DEFAULT);

  useEffect(() => {
    if (sample) return;
    let active = true;

    async function poll() {
      try {
        const res = await fetch(`${API_BASE_URL}/api/ibkr/status`);
        if (res.ok && active) {
          setStatus(await res.json());
        }
      } catch {
        // Gateway not running or IBKR disabled — keep showing disconnected
      }
    }

    poll();
    const id = setInterval(poll, 5_000);
    window.addEventListener(REFRESH_EVENT, poll);
    return () => {
      active = false;
      clearInterval(id);
      window.removeEventListener(REFRESH_EVENT, poll);
    };
  }, [sample]);

  if (sample) return SAMPLE_STATUS;
  return status;
}
