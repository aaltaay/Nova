import { useEffect, useState, useSyncExternalStore } from 'react';
import { novaWindowTitle, resolveNovaTitleDesk } from '../../electron/appTitle.mjs';
import { getRecordingSymbols, subscribeSessionRecord } from '../capture/sessionRecordStore';
import { parseSampleSymbol } from '../sample_data/sampleNav';
import { isElectronRenderer, nudgeElectronPaint } from './nudgeElectronPaint';
import { novaRendererReleaseTag } from './novaReleaseTag';

/** Keep document.title (and the Electron window title) on the current desk view. */
export function useNovaWindowTitle(
  traderActive: boolean,
  traderSymbol: string | null,
): void {
  const releaseTag = novaRendererReleaseTag();
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
    });
    if (traderActive && isElectronRenderer()) {
      nudgeElectronPaint();
    }
  }, [traderActive, traderSymbol, releaseTag, recordingSymbol]);
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
