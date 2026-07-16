import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from '../constants';
import type { DebugDecisionRow, DebugSnapRow } from './HodMomoDebugTables';
import type { Counters } from './hodMomoDebugTypes';

const API = `${API_BASE_URL}/api`;

export function useHodMomoDebugPoll() {
  const [counters, setCounters] = useState<Counters | null>(null);
  const [countersAge, setCountersAge] = useState(0);
  const [countersUpdated, setCountersUpdated] = useState(0);
  const [decisions, setDecisions] = useState<DebugDecisionRow[]>([]);
  const [snaps, setSnaps] = useState<DebugSnapRow[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function fetchCounters() {
    try {
      const r = await fetch(`${API}/hod-momo/debug/counters`);
      const d = await r.json();
      setCounters(d);
      setCountersUpdated(Date.now());
    } catch {
      /* network blip — next poll retries */
    }
  }

  async function fetchDecisions() {
    try {
      const r = await fetch(`${API}/hod-momo/debug/recent?limit=50`);
      const d = await r.json();
      setDecisions((d.decisions ?? []).slice().reverse());
    } catch {
      /* network blip — next poll retries */
    }
  }

  async function fetchSnaps() {
    try {
      const r = await fetch(`${API}/hod-momo/debug/snaps?limit=50`);
      const d = await r.json();
      setSnaps(d.snaps ?? []);
    } catch {
      /* network blip — next poll retries */
    }
  }

  useEffect(() => {
    void fetchCounters();
    void fetchDecisions();
    void fetchSnaps();

    timerRef.current = setInterval(() => {
      void fetchCounters();
      void fetchDecisions();
      void fetchSnaps();
      setCountersAge(Math.round((Date.now() - countersUpdated) / 1000));
    }, 2000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const t = setInterval(() => {
      setCountersAge(Math.round((Date.now() - countersUpdated) / 1000));
    }, 1000);
    return () => clearInterval(t);
  }, [countersUpdated]);

  return { counters, countersAge, decisions, snaps };
}
