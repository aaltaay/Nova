import { useEffect } from 'react';
import { novaWindowTitle } from '../../electron/appTitle.mjs';
import { novaRendererReleaseTag } from './novaReleaseTag';

/** Keep document.title (and the Electron window title) on the current desk view. */
export function useNovaWindowTitle(
  traderActive: boolean,
  traderSymbol: string | null,
): void {
  const releaseTag = novaRendererReleaseTag();
  useEffect(() => {
    document.title = novaWindowTitle({
      traderActive,
      traderSymbol: traderSymbol ?? '',
      releaseTag,
    });
  }, [traderActive, traderSymbol, releaseTag]);
}
