import { useEffect, useState } from 'react';
import { API_BASE_URL } from '../constants';
import type { IbkrStatus } from './types';

const DEFAULT: IbkrStatus = { enabled: false, connected: false, mode: 'disconnected' };

/** Polls /api/ibkr/status every 5 s to reflect IB Gateway connection state. */
export function useIbkrStatus(): IbkrStatus {
  const [status, setStatus] = useState<IbkrStatus>(DEFAULT);

  useEffect(() => {
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
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  return status;
}
