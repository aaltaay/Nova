/**
 * Sample-shell HOD owner — fixtures only, never opens live WS.
 */
import { useMemo, type ReactNode } from 'react';
import { useSampleData } from '../sample_data/SampleDataContext';
import {
  HodMomoContextProvider,
  useHodMomoDockState,
  type HodMomoContextValue,
} from './HodMomoContext';
import type { useHodMomoConfig } from './useHodMomoConfig';
import type { useHodMomoStream } from './useHodMomoStream';

export function HodMomoFixtureProvider({ children }: { children: ReactNode }) {
  const sample = useSampleData();

  const stream = useMemo(
    () =>
      ({
        alerts: sample.hodAlerts,
        totalToday: sample.hodAlerts.length,
        connected: true,
      }) as ReturnType<typeof useHodMomoStream>,
    [sample.hodAlerts],
  );

  const config = useMemo(
    () =>
      ({
        state: sample.hodConfig,
        updateStrategy: () => {},
        updateMaster: () => {},
        resetStrategy: async () => {},
        resetAll: async () => {},
      }) as ReturnType<typeof useHodMomoConfig>,
    [sample.hodConfig],
  );

  const dock = useHodMomoDockState(stream);

  const value = useMemo<HodMomoContextValue>(
    () => ({
      stream,
      config,
      ...dock,
    }),
    [stream, config, dock],
  );

  return (
    <HodMomoContextProvider value={value}>{children}</HodMomoContextProvider>
  );
}
