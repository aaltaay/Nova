/**
 * Live HOD Momo alerts as they arrive, for listeners outside the strip (the
 * operator's watch list toasts). Only a socket `alert` frame the stream has not
 * seen publishes: the `initial` snapshot, a reconnect's replay of the day and
 * the Sim playhead's history never do, so nothing old is announced as new.
 */
import type { AlertObject } from './types';

type Listener = (alert: AlertObject) => void;

const listeners = new Set<Listener>();

export function publishHodMomoLiveAlert(alert: AlertObject): void {
  for (const listener of listeners) {
    try {
      listener(alert);
    } catch (err) {
      // One bad listener must not stop the strip or the others.
      console.warn('[Nova] HOD Momo live-alert listener failed', err);
    }
  }
}

export function subscribeHodMomoLiveAlerts(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
