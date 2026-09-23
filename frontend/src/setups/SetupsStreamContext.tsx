/** One `/ws/setups` socket for the whole desk (ADR 022). The provider sits near
 * the app root so a proposal pings, and shows its alert card, on any tab; pop-out
 * desks pass `enabled={false}` so one proposal never rings twice. */
import { createContext, useContext, type ReactNode } from 'react';
import { SetupsAlertCard } from './SetupsAlertCard';
import { useSetupsStream, type SetupsStreamState } from './useSetupsStream';

const SetupsStreamContext = createContext<SetupsStreamState | null>(null);

export function SetupsStreamProvider({ enabled, children }: { enabled: boolean; children: ReactNode }) {
  const stream = useSetupsStream(enabled);
  return (
    <SetupsStreamContext.Provider value={enabled ? stream : null}>
      {children}
      {enabled && <SetupsAlertCard board={stream.board} />}
    </SetupsStreamContext.Provider>
  );
}

/** The desk's Setups board, or null outside the provider / in a pop-out desk. */
export function useSetupsBoard(): SetupsStreamState | null {
  return useContext(SetupsStreamContext);
}
