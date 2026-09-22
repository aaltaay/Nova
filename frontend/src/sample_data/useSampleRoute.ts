/**
 * The sample route as a React value (V4). Providers above the sample shell --
 * WorkspaceProvider, the header's pollers -- never see SampleDataProvider, so
 * they read the URL instead, and re-render when enterSampleView /
 * leaveSampleView announce the change with a popstate event.
 */
import { useSyncExternalStore } from 'react';
import { isSampleView } from './sampleNav';

export function subscribeSampleRoute(listener: () => void): () => void {
  if (typeof window === 'undefined') return () => {};
  window.addEventListener('popstate', listener);
  return () => window.removeEventListener('popstate', listener);
}

const readSampleRoute = (): boolean => isSampleView();
const serverSampleRoute = (): boolean => false;

/** True on ?view=sample (and its Trader route); false everywhere else. */
export function useSampleRoute(): boolean {
  return useSyncExternalStore(subscribeSampleRoute, readSampleRoute, serverSampleRoute);
}
