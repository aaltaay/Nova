/**
 * Sim tab truth strip -- sits directly under the SIM PRACTICE banner so the
 * state of the desk is read, not inferred from which panels happen to be blank.
 */
import { useCallback, useSyncExternalStore } from 'react';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { useWorkspace } from '../workspace';
import { simClockResource } from './simClockResource';
import { simReplayTarget } from './simReplayTarget';
import {
  SIM_TAB_NO_REPLAY_BODY,
  SIM_TAB_NO_REPLAY_TITLE,
  SIM_TAB_OTHER_SYMBOL_TITLE,
  SIM_TAB_REPLAY_FAILED_TITLE,
  simTabGoToReplayLabel,
  simTabOtherSymbolBody,
} from './simConstants';
import './simReplayTargetNotice.css';

export function SimReplayTargetNotice({ symbol }: { symbol: string }) {
  const sim = useIbkrStatus().mode === 'sim';
  const { openStockView } = useWorkspace();
  const subscribe = useCallback(
    (listener: () => void) => (sim ? simClockResource.subscribe(listener) : () => {}),
    [sim],
  );
  const state = useSyncExternalStore(subscribe, simClockResource.getSnapshot);
  const target = simReplayTarget(symbol, sim ? state.data : null, sim);
  if (target.kind === 'ok') return null;

  const tab = symbol.trim().toUpperCase();
  const title = target.kind === 'none'
    ? SIM_TAB_NO_REPLAY_TITLE
    : target.kind === 'failed'
      ? SIM_TAB_REPLAY_FAILED_TITLE
      : SIM_TAB_OTHER_SYMBOL_TITLE;
  const body = target.kind === 'none'
    ? SIM_TAB_NO_REPLAY_BODY
    : target.kind === 'failed'
      ? target.error
      : simTabOtherSymbolBody(tab, target.replaySymbol);

  return (
    <div
      className={`sim-replay-target sim-replay-target--${target.kind}`}
      role="status"
      data-testid="sim-replay-target-notice"
    >
      <strong className="sim-replay-target__title">{title}</strong>
      <span className="sim-replay-target__body">{body}</span>
      {target.kind === 'other-symbol' && (
        <button
          type="button"
          className="sim-replay-target__action"
          data-testid="sim-replay-target-goto"
          onClick={() => openStockView(target.replaySymbol)}
        >
          {simTabGoToReplayLabel(target.replaySymbol)}
        </button>
      )}
    </div>
  );
}
