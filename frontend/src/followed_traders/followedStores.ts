/**
 * Two small per-window stores for the Followed traders page: the Alerts switch (kept in local storage, a per-window
 * convenience, on by default; storage that throws reads as on) and a request to open one trade's proof (a toast
 * asks, the page takes it).
 */
import { useSyncExternalStore } from 'react';
import { FOLLOWED_ALERTS_KEY } from './constants';

type Listener = () => void;

function store<T>(initial: T) {
  let value = initial;
  const listeners = new Set<Listener>();
  return {
    get: () => value,
    set(next: T) {
      if (Object.is(next, value)) return;
      value = next;
      listeners.forEach((l) => l());
    },
    subscribe(l: Listener) {
      listeners.add(l);
      return () => { listeners.delete(l); };
    },
  };
}

function readAlerts(): boolean {
  try {
    return window.localStorage.getItem(FOLLOWED_ALERTS_KEY) !== 'off';
  } catch {
    return true;
  }
}

const alerts = store<boolean>(typeof window === 'undefined' ? true : readAlerts());

export function setFollowedAlerts(on: boolean): void {
  try {
    window.localStorage.setItem(FOLLOWED_ALERTS_KEY, on ? 'on' : 'off');
  } catch {
    // Storage blocked: the switch still holds for this window.
  }
  alerts.set(on);
}

export function useFollowedAlerts(): boolean {
  return useSyncExternalStore(alerts.subscribe, alerts.get, alerts.get);
}

export interface ProofRequest {
  date: string;
  tradeId: string;
}

const proof = store<ProofRequest | null>(null);

export function requestFollowedProof(req: ProofRequest): void {
  proof.set(req);
}

export function clearFollowedProofRequest(): void {
  proof.set(null);
}

export function useFollowedProofRequest(): ProofRequest | null {
  return useSyncExternalStore(proof.subscribe, proof.get, proof.get);
}

export function resetFollowedStoresForTests(): void {
  alerts.set(true);
  proof.set(null);
}
