/**
 * Live AppShell owner of HOD Momo stream + config + dock prefs.
 * Mount above Scanner/Trader fork so Trader does not tear down the WS.
 * On Sim off the live edge the strip reads the alert history at the playhead
 * instead of the live socket (ADR 022, one desk, one clock); the socket stays
 * open underneath so the live edge is instant.
 */
import { useMemo, type ReactNode } from 'react';
import {
  HodMomoContextProvider,
  useHodMomoDockState,
  type HodMomoContextValue,
} from './HodMomoContext';
import { useHodMomoConfig } from './useHodMomoConfig';
import { useHodMomoReplay } from './useHodMomoReplay';
import { useHodMomoStream } from './useHodMomoStream';

export function HodMomoProvider({ children }: { children: ReactNode }) {
  const live = useHodMomoStream();
  const replay = useHodMomoReplay();
  const stream = useMemo(
    () => (replay
      ? { alerts: replay.alerts, totalToday: replay.alerts.length, connected: true, feedError: replay.state.error }
      : live),
    [live, replay],
  );
  const config = useHodMomoConfig();
  const dock = useHodMomoDockState(stream);

  const value = useMemo<HodMomoContextValue>(
    () => ({
      stream,
      config,
      ...dock,
      replay: replay?.state ?? null,
    }),
    [stream, config, dock, replay],
  );

  return (
    <HodMomoContextProvider value={value}>{children}</HodMomoContextProvider>
  );
}
