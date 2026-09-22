/** Whether empty REST bars may fall back to synthetic mock candles. */

export function allowMockBarsFallback(discoveryProvider: string): boolean {
  // Under IBKR discovery, mock bars would look like an IBKR quote — forbidden.
  return discoveryProvider !== 'ibkr';
}

export function emptyBarsMessage(discoveryProvider: string): string {
  if (discoveryProvider === 'ibkr') {
    return 'No IBKR historical bars available for this symbol/timeframe.';
  }
  return 'No chart bars available.';
}

/**
 * An empty chart is a stated absence, never a red error (QA V9). The words say
 * why the pane is empty: on Sim with nothing loaded there is no "replay time"
 * at all, and another symbol's replay will never fill this one.
 */
export const CHART_EMPTY_NO_REPLAY = 'No replay loaded -- nothing to chart here';
export const CHART_EMPTY_REPLAY_TIME = 'No bars at this replay time';
export const CHART_EMPTY_REPLAY_FAILED = 'The replay did not load -- no bars to chart';
export function chartEmptyOtherSymbol(replaySymbol: string): string {
  return `${replaySymbol} is the loaded replay -- no bars for this symbol`;
}

export type ChartEmptyTarget =
  | { kind: 'ok' | 'live-edge' | 'none' }
  | { kind: 'other-symbol'; replaySymbol: string }
  | { kind: 'failed'; error: string };

export function chartEmptyText(sim: boolean, target: ChartEmptyTarget, discoveryProvider: string): string {
  if (!sim || target.kind === 'live-edge') return emptyBarsMessage(discoveryProvider);
  if (target.kind === 'none') return CHART_EMPTY_NO_REPLAY;
  if (target.kind === 'other-symbol') return chartEmptyOtherSymbol(target.replaySymbol);
  if (target.kind === 'failed') return CHART_EMPTY_REPLAY_FAILED;
  return CHART_EMPTY_REPLAY_TIME;
}
