/**
 * Sim tab prompt -- a state inside the quote / ladder card (never a band over
 * the page, operator decision 2026-09-21).
 *
 * A Sim tab without its replay says so in one line and offers the one action
 * that fixes it: Download (then it loads itself), Load, Resume, Retry -- or, with
 * Gateway not running, Start Gateway & download. The × hides the prompt for this
 * tab and situation; it never cancels a download or a queued heal. At the live
 * edge the strip's `Live edge` pill already says the tab is live, so this
 * renders nothing there.
 */
import { useCallback, useState, useSyncExternalStore } from 'react';
import { useWorkspace } from '../workspace';
import { durationLabel } from './historicalProgress';
import { useSimReplayTarget } from './useSimReplayTarget';
import { offerCopy, type OfferAction } from './simReplayOffer';
import { useSimReplayOffer } from './useSimReplayOffer';
import { etDateToday, ownRecordingFor } from './ownRecording';
import { capturesResource } from './useSimSessionController';
import {
  SIM_TAB_ACTION_DOWNLOAD,
  SIM_TAB_ACTION_LOAD,
  SIM_TAB_ACTION_LOADING,
  SIM_TAB_ACTION_RECONNECT,
  SIM_TAB_ACTION_RESUME,
  SIM_TAB_ACTION_RETRY,
  SIM_TAB_ACTION_START_GATEWAY,
  SIM_TAB_ACTION_STARTING,
  SIM_TAB_ACTION_STOP,
  SIM_TAB_ACTION_STOP_OTHER,
  SIM_TAB_CHARTS_ARCHIVED,
  SIM_TAB_DISMISS_LABEL,
  SIM_TAB_NO_REPLAY_TITLE,
  SIM_TAB_NO_WINDOW,
  SIM_TAB_OTHER_SYMBOL_TITLE,
  SIM_TAB_REPLAY_FAILED_TITLE,
  SIM_TAB_WHAT_SIM_IS,
  SIM_WHY_TAB_STARTING,
  SIM_WHY_TAB_STOPPING,
  SIM_WHY_TAB_STOPPING_OTHER,
  SIM_WHY_WINDOW_LOADING,
  simTabGoToReplayLabel,
  simTabOfferBusy,
  simTabOfferDownload,
  simTabOfferDownloading,
  simTabOfferFailed,
  simTabOfferGatewayDown,
  simTabOfferGatewayWaiting,
  simTabOfferNotAnswering,
  simTabOfferNotAnsweringGaveUp,
  simTabOfferReady,
  simTabOfferRetrying,
  simTabOfferStopped,
  simTabOtherSymbolLead,
  simTabOwnRecording,
} from './simConstants';
import './simReplayTargetNotice.css';

const COPY = {
  download: simTabOfferDownload,
  ready: simTabOfferReady,
  downloading: simTabOfferDownloading,
  stopped: simTabOfferStopped,
  failed: simTabOfferFailed,
  busy: simTabOfferBusy,
  gatewayDown: simTabOfferGatewayDown,
  gatewayWaiting: simTabOfferGatewayWaiting,
  retrying: simTabOfferRetrying,
  notAnswering: simTabOfferNotAnswering,
  notAnsweringGaveUp: simTabOfferNotAnsweringGaveUp,
  duration: durationLabel,
};

const ACTION_LABEL: Record<OfferAction, string> = {
  download: SIM_TAB_ACTION_DOWNLOAD,
  load: SIM_TAB_ACTION_LOAD,
  resume: SIM_TAB_ACTION_RESUME,
  retry: SIM_TAB_ACTION_RETRY,
  'start-gateway': SIM_TAB_ACTION_START_GATEWAY,
  stop: SIM_TAB_ACTION_STOP,
  'stop-other': SIM_TAB_ACTION_STOP_OTHER,
  reconnect: SIM_TAB_ACTION_RECONNECT,
};

/** Per tab + situation, for the session: a new situation earns a new prompt. */
const dismissed = new Set<string>();

export function SimReplayTargetNotice({ symbol }: { symbol: string }) {
  const { openStockView } = useWorkspace();
  const { clock, target } = useSimReplayTarget(symbol);
  const wantsReplay = target.kind === 'none' || target.kind === 'other-symbol';
  const { offer, download, startGateway, reconnect, stop, load, starting, loading, error } = useSimReplayOffer(
    symbol, clock, wantsReplay, target.kind === 'none',
  );
  const [, setDismissTick] = useState(0);
  // Only a Sim tab with nothing loaded reads the capture archive -- a Paper or
  // Live Stock View never polls it.
  const wantsOwn = target.kind === 'none';
  const subscribeCaptures = useCallback(
    (listener: () => void) => (wantsOwn ? capturesResource.subscribe(listener) : () => {}),
    [wantsOwn],
  );
  const captures = useSyncExternalStore(subscribeCaptures, capturesResource.getSnapshot);
  // The desk's day first: after a Day jump the playhead is on a past day, not today (ADR 023).
  const own = wantsOwn ? ownRecordingFor(captures.data, symbol, etDateToday(), clock?.session_date) : null;

  const tab = symbol.trim().toUpperCase();
  const dismissKey = `${tab}|${target.kind}`;
  // The tab is live at the edge: the strip's pill says so; nothing to offer, nothing to fetch.
  // A capture still loading is said by the strip's pill too -- never offered a download meanwhile.
  if (target.kind === 'ok' || target.kind === 'live-edge' || target.kind === 'loading' || dismissed.has(dismissKey)) return null;

  const instead = target.kind === 'other-symbol';
  const title = target.kind === 'none'
    ? SIM_TAB_NO_REPLAY_TITLE
    : target.kind === 'failed' ? SIM_TAB_REPLAY_FAILED_TITLE : SIM_TAB_OTHER_SYMBOL_TITLE;
  const copy = offer ? offerCopy(offer, instead, COPY) : null;
  const run = () => {
    if (!offer || !copy?.action) return;
    if (copy.action === 'stop') { if (offer.kind === 'downloading') void stop(offer.jobId); return; }
    if (copy.action === 'stop-other') { if (offer.kind === 'busy') void stop(offer.runningJobId, offer.window); return; }
    const act = copy.action === 'load' ? load
      : copy.action === 'start-gateway' ? startGateway
        : copy.action === 'reconnect' ? reconnect : download;
    void act(offer.window);
  };
  const actionLabel = copy?.action
    ? starting ? SIM_TAB_ACTION_STARTING : loading ? SIM_TAB_ACTION_LOADING : ACTION_LABEL[copy.action]
    : null;
  // Why the action is locked (ux/whyTip.ts): the request it sent is still in flight.
  const actionWhy = starting
    ? copy?.action === 'stop' ? SIM_WHY_TAB_STOPPING
      : copy?.action === 'stop-other' ? SIM_WHY_TAB_STOPPING_OTHER : SIM_WHY_TAB_STARTING
    : loading ? SIM_WHY_WINDOW_LOADING : null;

  return (
    <div
      className={`sim-replay-target sim-replay-target--${target.kind}`}
      role="status"
      data-testid="sim-replay-target-notice"
      title={wantsReplay ? SIM_TAB_CHARTS_ARCHIVED : undefined}
    >
      <strong className="sim-replay-target__title">{title}</strong>
      <span className="sim-replay-target__body" data-testid="sim-replay-target-body">
        {target.kind === 'failed' && target.error}
        {target.kind === 'other-symbol' && `${simTabOtherSymbolLead(tab, target.replaySymbol)} `}
        {wantsReplay && (copy ? copy.text : SIM_TAB_NO_WINDOW)}
      </span>
      {own && (
        <span className="sim-replay-target__body" data-testid="sim-replay-own-recording">
          {simTabOwnRecording(own.symbol, own.date, own.prints, own.recording)}
        </span>
      )}
      {target.kind === 'none' && (
        <span className="sim-replay-target__body" data-testid="sim-replay-what-sim-is">{SIM_TAB_WHAT_SIM_IS}</span>
      )}
      {error && <span role="alert" className="sim-replay-target__error">{error}</span>}
      <span className="sim-replay-target__actions">
        {actionLabel && (
          // Locked, title '' keeps the card's own title from showing over the reason.
          <button
            type="button"
            className="sim-replay-target__action"
            data-testid="sim-replay-target-action"
            disabled={starting || loading}
            data-why={actionWhy ?? undefined}
            title={actionWhy ? '' : undefined}
            onClick={run}
          >
            {actionLabel}
          </button>
        )}
        {target.kind === 'other-symbol' && (
          <button
            type="button"
            className="sim-replay-target__action sim-replay-target__action--secondary"
            data-testid="sim-replay-target-goto"
            onClick={() => openStockView(target.replaySymbol)}
          >
            {simTabGoToReplayLabel(target.replaySymbol)}
          </button>
        )}
        <button
          type="button"
          className="sim-replay-target__dismiss"
          data-testid="sim-replay-target-dismiss"
          aria-label={SIM_TAB_DISMISS_LABEL}
          title={SIM_TAB_DISMISS_LABEL}
          onClick={() => { dismissed.add(dismissKey); setDismissTick(n => n + 1); }}
        >
          ×
        </button>
      </span>
    </div>
  );
}

/** Test seam: dismissals are session-scoped module state. */
export function resetSimReplayTargetDismissals(): void {
  dismissed.clear();
}
