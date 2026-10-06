/** An in-flight real-desk reply cannot survive a visit to the sample desk. */
import { isSampleView } from '../sample_data/sampleNav';

export function watchDeskRequestRoute(): { isCurrent: () => boolean; dispose: () => void } {
  let sample = isSampleView();
  let changed = false;
  const onRoute = () => {
    const next = isSampleView();
    if (next !== sample) changed = true;
    sample = next;
  };
  if (typeof window !== 'undefined') window.addEventListener('popstate', onRoute);
  return {
    isCurrent: () => !changed && !isSampleView(),
    dispose: () => {
      if (typeof window !== 'undefined') window.removeEventListener('popstate', onRoute);
    },
  };
}
