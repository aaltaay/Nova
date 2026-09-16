/**
 * Overlay gates for Trading prerequisites -- streak + in-flight Place.
 */
import { useEffect, useState } from 'react';
import type { HealthStatus } from '../types/health';
import {
  deskActionInFlight,
  subscribeDeskAction,
} from './deskActionFlight';
import { novaApiOk } from './tradingPrerequisites';

export function usePrereqOverlayInputs(health: HealthStatus) {
  const [apiFailStreak, setApiFailStreak] = useState(0);
  const [deskBusy, setDeskBusy] = useState(() => deskActionInFlight());

  useEffect(() => {
    if (novaApiOk(health)) {
      setApiFailStreak(0);
      return;
    }
    setApiFailStreak((n) => n + 1);
  }, [
    health.status,
    health.flag,
    health.latency_ms,
    health.ib_loop_lag_ms?.wedged,
  ]);

  useEffect(() => subscribeDeskAction(() => {
    setDeskBusy(deskActionInFlight());
  }), []);

  return {
    apiFailStreak,
    deskActionInFlight: deskBusy,
  };
}
