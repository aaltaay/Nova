/**
 * Overlay gates for Trading prerequisites -- streak + in-flight Place + Record.
 */
import { useEffect, useState, useSyncExternalStore } from 'react';
import type { HealthStatus } from '../types/health';
import {
  deskActionInFlight,
  subscribeDeskAction,
} from './deskActionFlight';
import { novaApiOk } from './tradingPrerequisites';
import {
  getRecordingSymbols,
  subscribeSessionRecord,
} from '../capture/sessionRecordStore';

export function usePrereqOverlayInputs(health: HealthStatus) {
  const [apiFailStreak, setApiFailStreak] = useState(0);
  const [deskBusy, setDeskBusy] = useState(() => deskActionInFlight());
  const recordingEpoch = useSyncExternalStore(
    subscribeSessionRecord,
    () => getRecordingSymbols().join(','),
    () => '',
  );

  const apiOk = novaApiOk(health);

  useEffect(() => {
    if (apiOk) {
      setApiFailStreak(0);
      return;
    }
    setApiFailStreak((n) => n + 1);
  }, [health, apiOk]);

  useEffect(() => subscribeDeskAction(() => {
    setDeskBusy(deskActionInFlight());
  }), []);

  return {
    apiFailStreak,
    deskActionInFlight: deskBusy,
    sessionRecording: recordingEpoch.length > 0,
  };
}
