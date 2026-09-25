import { useEffect, useState, useSyncExternalStore } from 'react';
import { novaWindowTitle, resolveNovaTitleDesk } from '../../electron/appTitle.mjs';
import { getRecordingSymbols, subscribeSessionRecord } from '../capture/sessionRecordStore';
import { parseSampleSymbol } from '../sample_data/sampleNav';
import { useBackendCheckoutTag, useBackendReleaseTag } from './backendReleaseTag';
import { isElectronRenderer, nudgeElectronPaint } from './nudgeElectronPaint';
import { novaRendererReleaseTag } from './novaReleaseTag';

/** Keep document.title (and the Electron window title) on the current desk view. */
export function useNovaWindowTitle(
  traderActive: boolean,
  traderSymbol: string | null,
): void {
  const releaseTag = novaRendererReleaseTag();
  // The backend's own revision beside the desk's: an update leaves a running backend on its old code.
  const backendTag = useBackendReleaseTag();
  // What a restart would load: says whether the older backend needs a pull first.
  const checkoutTag = useBackendCheckoutTag();
  // The OS title says REC while a recording runs -- the one signal that
  // survives the app being behind other windows.
  const recordingSymbol = useSyncExternalStore(
    subscribeSessionRecord,
    () => getRecordingSymbols().join(', '),
    () => '',
  );
  useEffect(() => {
    document.title = novaWindowTitle({
      traderActive,
      traderSymbol: traderSymbol ?? '',
      releaseTag,
      recordingSymbol,
      backendTag: backendTag ?? '',
      checkoutTag: checkoutTag ?? '',
    });
    if (traderActive && isElectronRenderer()) {
      nudgeElectronPaint();
    }
  }, [traderActive, traderSymbol, releaseTag, recordingSymbol, backendTag, checkoutTag]);
}

/** Sample `?view=sample&symbol=` is Trader; live uses the Scanner|Trader switch. */
export function useNovaDeskWindowTitle(
  sampleMode: boolean,
  liveTraderActive: boolean,
  liveTraderSymbol: string | null,
): void {
  const [sampleSymbol, setSampleSymbol] = useState(() => parseSampleSymbol());
  useEffect(() => {
    const sync = () => setSampleSymbol(parseSampleSymbol());
    sync();
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, [sampleMode]);
  const desk = resolveNovaTitleDesk({
    sampleMode,
    sampleSymbol: sampleSymbol ?? '',
    liveTraderActive,
    liveTraderSymbol: liveTraderSymbol ?? '',
  });
  useNovaWindowTitle(desk.traderActive, desk.traderSymbol);
}
