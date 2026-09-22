/**
 * "Download and load" for one Sim tab, healing itself where it can.
 *
 * - Download starts the same trades job the Historical replay panel would; at
 *   its first committed page the window loads itself and keeps growing
 *   (useProgressiveReplay) -- only a window THIS tab asked for, and only while
 *   the tab is open, so nothing loads behind the operator's back.
 * - Gateway not running: the button becomes "Start Gateway & download". That
 *   click is the operator's consent to launch (gateway_heal never auto-logs in);
 *   everything after it -- wait for a port, download, load -- is automatic.
 * - A download that failed only because Gateway was unreachable retries on its
 *   own once a port answers, honouring the backend's retry throttle, a bounded
 *   number of times before it hands the Retry button back.
 */
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { launchIbGateway } from '../utils/launchIbGateway';
import { historicalStatus } from './historicalStatusStore';
import { selectHistoricalReplay } from './historicalReplayLoad';
import { gatewayReachable, offerWindow, replayOffer, windowKey, type ReplayOffer } from './simReplayOffer';
import { SIM_TAB_HEAL_MAX_ATTEMPTS, SIM_TAB_NOT_ANSWERING_MAX_ATTEMPTS } from './simConstants';
import { useReplayActions } from './useReplayActions';
import type { HistoricalJob, HistoricalWindow } from './historicalTypes';
import type { SimClockState } from './simClockTypes';

/** `key` = the window the launch was requested for; waiting belongs to that window only. */
interface LaunchState { waiting: boolean; message: string | null; key: string | null }

export function useSimReplayOffer(
  symbol: string,
  clock: SimClockState | null,
  enabled: boolean,
  /** Nothing is loaded: filling the empty desk disturbs nothing, so a healed retry may load. */
  deskEmpty: boolean,
) {
  // Conditional subscription: Paper/Live Stock Views must not poll the archive.
  const subscribe = useCallback(
    (listener: () => void) => (enabled ? historicalStatus.subscribe(listener) : () => {}),
    [enabled],
  );
  const status = useSyncExternalStore(subscribe, historicalStatus.getSnapshot);
  const reachable = gatewayReachable(useIbkrStatus());
  const { request, busy, errors } = useReplayActions();
  const intent = useRef<string | null>(null);
  const [healAttempts, setHealAttempts] = useState(0);
  const [launch, setLaunch] = useState<LaunchState>({ waiting: false, message: null, key: null });

  const window = enabled ? offerWindow(symbol, clock, status.data) : null;
  const jobs = Array.isArray(status.data?.jobs) ? status.data.jobs : [];
  const base = window ? replayOffer(window, jobs, reachable) : null;
  const key = window ? windowKey(window) : null;

  const load = useCallback(async (spec: HistoricalWindow) => {
    intent.current = null;
    await selectHistoricalReplay(request, spec);
  }, [request]);

  const download = useCallback(async (spec: HistoricalWindow) => {
    // Idempotent per window: resumes a stopped job, returns a finished one as-is.
    const job = await request<HistoricalJob>('download', '/history', { ...spec, kind: 'trades' });
    if (!job) return;
    void historicalStatus.refresh();
    if (job.status === 'complete' && intent.current === windowKey(spec)) await load(spec);
  }, [request, load]);

  const requestDownload = useCallback(async (spec: HistoricalWindow) => {
    intent.current = windowKey(spec);
    setHealAttempts(0);
    await download(spec);
  }, [download]);

  /**
   * Abandon a download whose cost the operator has now seen; it stays resumable.
   * With `then`, this tab's window starts as soon as the freed slot shows up --
   * the queued-download effect below picks it up from `intent`.
   */
  const stop = useCallback(async (jobId: string, then?: HistoricalWindow) => {
    intent.current = then ? windowKey(then) : null;
    if (then) setHealAttempts(0);
    if (await request('download', `/history/${encodeURIComponent(jobId)}/pause`)) {
      void historicalStatus.refresh();
    } else if (then) {
      intent.current = null;
    }
  }, [request]);

  const startGateway = useCallback(async (spec: HistoricalWindow) => {
    const launchKey = windowKey(spec);
    intent.current = launchKey;
    setHealAttempts(0);
    setLaunch({ waiting: true, message: null, key: launchKey });
    const result = await launchIbGateway();
    setLaunch({ waiting: result.ok, message: result.ok ? null : result.message, key: launchKey });
  }, []);

  /**
   * Gateway took the connection but IBKR is silent: ask the backend to rebuild
   * Nova's session (launch-gateway does exactly that when the port already
   * listens), then try the download again straight away.
   */
  const reconnect = useCallback(async (spec: HistoricalWindow) => {
    const launchKey = windowKey(spec);
    intent.current = launchKey;
    setHealAttempts(0);
    const result = await launchIbGateway();
    setLaunch({ waiting: false, message: result.ok ? null : result.message, key: launchKey });
    if (result.ok) await download(spec);
  }, [download]);

  const kind = base?.kind;
  const failed = base?.kind === 'failed' ? base : null;
  // Two healable failures: Gateway was down (retry once a port answers) and
  // Gateway took the connection but IBKR never answered (retry slowly -- a stuck
  // session or maintenance -- whatever the ports say).
  const notAnswering = Boolean(failed?.gatewayNotAnswering);
  const maxAttempts = notAnswering ? SIM_TAB_NOT_ANSWERING_MAX_ATTEMPTS : SIM_TAB_HEAL_MAX_ATTEMPTS;
  const healable = (notAnswering || (Boolean(failed?.gatewayUnreachable) && reachable))
    && healAttempts < maxAttempts;
  const retryAt = failed?.retryAt ?? null;

  // Gateway came up after "Start Gateway & download": run the queued download.
  useEffect(() => {
    if (!reachable) return;
    setLaunch(prev => (prev.waiting ? { waiting: false, message: null, key: null } : prev));
    if (window && key && intent.current === key && (kind === 'download' || kind === 'stopped')) {
      void download(window);
    }
    // `window` is rebuilt every render; `key` is its identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reachable, kind, key, download]);

  // Heal: a Gateway-unreachable failure retries itself once a port answers.
  useEffect(() => {
    if (!window || !key || !healable) return undefined;
    const delay = retryAt == null ? 0 : Math.max(0, retryAt * 1000 - Date.now());
    const timer = setTimeout(() => {
      setHealAttempts(n => n + 1);
      // The original click was "download and load"; on an empty desk loading
      // the finished window is exactly that, so the heal carries the intent.
      if (deskEmpty) intent.current = key;
      void download(window);
    }, delay);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [healable, key, retryAt, deskEmpty, download]);

  // Load what this tab asked for as soon as there is anything to play -- the
  // first committed page, not the last (useProgressiveReplay folds in the rest).
  // A non-healable failure drops the ask.
  const hasCoverage = base?.kind === 'downloading' && base.hasCoverage;
  useEffect(() => {
    if (!window || !key || intent.current !== key) return;
    if (kind === 'ready' || hasCoverage) void load(window);
    else if (kind === 'failed' && !failed?.gatewayUnreachable && !failed?.gatewayNotAnswering) {
      intent.current = null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, key, hasCoverage, load]);

  let offer: ReplayOffer | null = base;
  if (base?.kind === 'gateway-down') offer = { ...base, waiting: launch.waiting && launch.key === key };
  else if (base?.kind === 'failed' && (healable || base.gatewayNotAnswering)) {
    offer = {
      ...base, healing: healable, attempt: healAttempts + 1, maxAttempts,
      gaveUp: Boolean(base.gatewayNotAnswering) && !healable,
    };
  }

  return {
    offer,
    download: requestDownload,
    startGateway,
    reconnect,
    stop,
    load,
    starting: busy.has('download'),
    loading: busy.has('select'),
    error: launch.message ?? errors.download ?? errors.select ?? null,
  };
}
