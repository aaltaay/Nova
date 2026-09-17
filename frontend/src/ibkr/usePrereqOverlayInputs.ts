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

  const apiOk = novaApiOk(health);

  useEffect(() => {
    if (apiOk) {
      setApiFailStreak(0);
      return;
    }
    setApiFailStreak((n) => n + 1);
    // `health` is the probe snapshot (memoized on bar.health). Each new
    // object that is still down increments the streak. `apiOk` alone would
    // stick at 1 and never overlay.
  }, [health, apiOk]);

  useEffect(() => subscribeDeskAction(() => {
    setDeskBusy(deskActionInFlight());
  }), []);

  return {
    apiFailStreak,
    deskActionInFlight: deskBusy,
  };
}
