/**
 * Ahead's MACD fan on the MACD pane under the 1-minute chart (ADR 065). `useMacdPane` hears whether that pane is
 * there (`chart/oscillatorRegistry.ts`: the pane publishes itself); the scene uses it to decide whether a fan is worked
 * out at all. `useAheadMacd` attaches the fan's primitive to the pane's MACD line while both exist and hands it the
 * scene's bands. The bands themselves are worked out once per answer in `aheadScene.ts`; nothing heavy runs here.
 */
import { useEffect, useRef, useState } from 'react';
import type { IChartApi } from 'lightweight-charts';
import { subscribeOscillatorPane, type OscillatorPaneHandle } from '../chart';
import { AheadMacdPrimitive } from './AheadMacdPrimitive';
import { AHEAD_WORDS } from './aheadConstants';
import type { AheadScene } from './aheadSceneTypes';

/** The MACD pane under `chart` while `enabled`; null when there is none. */
export function useMacdPane(chart: IChartApi | null, enabled: boolean): OscillatorPaneHandle | null {
  const [pane, setPane] = useState<OscillatorPaneHandle | null>(null);
  useEffect(() => {
    if (!enabled || !chart) {
      setPane(null);
      return undefined;
    }
    return subscribeOscillatorPane(chart, 'macd', setPane);
  }, [chart, enabled]);
  return pane;
}

export function useAheadMacd(pane: OscillatorPaneHandle | null, scene: AheadScene | null): void {
  const primitive = useRef<AheadMacdPrimitive | null>(null);
  const line = pane?.line ?? null;
  useEffect(() => {
    if (!line) return undefined;
    const p = new AheadMacdPrimitive();
    line.attachPrimitive(p);
    primitive.current = p;
    return () => {
      try {
        line.detachPrimitive(p);
      } catch {
        /* the MACD pane is gone with its chart */
      }
      if (primitive.current === p) primitive.current = null;
    };
  }, [line]);
  const anchorT = scene?.on ? scene.anchorT : null;
  const bands = scene?.on ? scene.macd : null;
  const horizon = scene?.horizon ?? 0;
  useEffect(() => {
    primitive.current?.setFan(anchorT === null || !bands
      ? null
      : { anchorT, horizon, bands, caption: AHEAD_WORDS.macdPaneLabel });
  }, [line, anchorT, bands, horizon]);
}
