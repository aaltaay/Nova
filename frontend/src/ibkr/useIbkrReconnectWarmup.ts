/**
 * Tracks a bounded "just reconnected" window after IBKR flips
 * disconnected → connected, so callers can distinguish a genuinely quiet
 * scanner from the ADR 008 roster/L1 resubscribe warm-up period.
 */
import { useEffect, useRef, useState } from 'react';
import { IBKR_RECONNECT_WARMUP_SEC } from './gatewayUxConstants';

/** True for IBKR_RECONNECT_WARMUP_SEC after `connected` last transitioned
 * from false to true. False before any transition and once the window elapses. */
export function useIbkrReconnectWarmup(connected: boolean): boolean {
  const wasConnectedRef = useRef(connected);
  const [warmingUp, setWarmingUp] = useState(false);

  useEffect(() => {
    const justReconnected = connected && !wasConnectedRef.current;
    wasConnectedRef.current = connected;

    if (!justReconnected) {
      if (!connected) setWarmingUp(false);
      return;
    }

    setWarmingUp(true);
    const timer = window.setTimeout(() => {
      setWarmingUp(false);
    }, IBKR_RECONNECT_WARMUP_SEC * 1000);
    return () => window.clearTimeout(timer);
  }, [connected]);

  return warmingUp;
}
