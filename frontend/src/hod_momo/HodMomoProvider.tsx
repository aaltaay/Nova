/**
 * Live AppShell owner of HOD Momo stream + config + dock prefs.
 * Mount above Scanner/Trader fork so Trader does not tear down the WS.
 */
import { useMemo, type ReactNode } from 'react';
import {
  HodMomoContextProvider,
  useHodMomoDockState,
  type HodMomoContextValue,
} from './HodMomoContext';
import { useHodMomoConfig } from './useHodMomoConfig';
import { useHodMomoStream } from './useHodMomoStream';

export function HodMomoProvider({ children }: { children: ReactNode }) {
  const stream = useHodMomoStream();
  const config = useHodMomoConfig();
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
