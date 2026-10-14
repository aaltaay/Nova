/**
 * Records -- the Session Records (Market data) and the video clips.
 *
 * Market data (operator ask 2026-10-14: "i need a way to turn off the
 * recording and i feel like this entire screen need better ux"): what records
 * now, with a held Stop each and Hold to stop all; auto-record's switch and
 * windows; then every day's Session Records from GET /api/capture/sessions
 * (shared poll resource with the Sim header) -- the newest day open, earlier
 * days folded. States are stated, never guessed: loading, unavailable, none
 * yet. Recording symbols come from a fresh status only, and counts Nova does
 * not know read as words, never "-1" (QA 2026-09-22, C13 / C14 / C22 / C64 / V20).
 * The pieces live in `pages/records/`; schema: recording-and-replay.md,
 * "The Records page and turning recording off".
 */
import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { RECORDING_SIGNAL_TICK_MS } from '../capture/constants';
import { useRecordingSymbols } from '../capture/sessionRecordStore';
import { ClipsList, CLIP_RECORDS_TAB_CLIPS, CLIP_RECORDS_TAB_SESSIONS, takeClipsListRequest, useClips } from '../clips';
import {
  RECORDS_PAGE_EMPTY,
  RECORDS_PAGE_ERROR_PREFIX,
  RECORDS_PAGE_LOADING,
  RECORDS_PAGE_REPLAY_FAILED,
  RECORDS_PAGE_TITLE,
} from '../constantGroups/nav_rail';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { selectCaptureReplay } from '../sim/captureReplayLoad';
import { useReplayActions } from '../sim/useReplayActions';
import { capturesResource, type CaptureSessionRow } from '../sim/useSimSessionController';
import { AutoRecordCard } from './records/AutoRecordCard';
import { RecordingNowCard } from './records/RecordingNowCard';
import { RecordsDayTable } from './records/RecordsDayTable';
import { recordsSavedTo } from './records/recordsConstants';
import { todayEasternDate } from './records/recordsModel';
import { useAutoRecordSwitch } from './records/useAutoRecordSwitch';
import '../styles/rail-pages.css';
import './records/records.css';

export { formatMissingSeconds, todayEasternDate } from './records/recordsModel';

interface Props {
  onOpenTrader: (symbol: string) => void;
}

/** Without a recording the page only needs its clock for the windows' "now" line. */
const IDLE_TICK_MS = 30_000;
const NO_DAYS: Record<string, CaptureSessionRow[]> = {};

export function RecordsPage({ onOpenTrader }: Props) {
  const { data, error } = useSyncExternalStore(capturesResource.subscribe, capturesResource.getSnapshot);
  const recordingSymbols = useRecordingSymbols();
  const recordingKey = recordingSymbols.join(',');
  const recording = useMemo(() => new Set(recordingKey ? recordingKey.split(',') : []), [recordingKey]);
  const status = useIbkrStatus();
  const sim = status.mode === 'sim';
  const control = useAutoRecordSwitch();
  const { request, busy, errors } = useReplayActions();
  const [replayError, setReplayError] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    setNowMs(Date.now());
    const id = window.setInterval(() => setNowMs(Date.now()), recording.size ? RECORDING_SIGNAL_TICK_MS : IDLE_TICK_MS);
    return () => window.clearInterval(id);
  }, [recording.size]);
  const today = todayEasternDate(new Date(nowMs));
  const byDay = data?.tickers_by_day ?? NO_DAYS;
  const days = Object.keys(byDay).filter(date => (byDay[date] ?? []).length > 0);
  const todayRows = new Map<string, CaptureSessionRow>((byDay[today] ?? []).map(row => [row.symbol, row]));
  const sessionCount = days.reduce((n, date) => n + (byDay[date] ?? []).length, 0);

  const replay = async (date: string, symbol: string) => {
    setReplayError(null);
    const result = await selectCaptureReplay(request, date, symbol);
    if (!result) return;
    if (result.clock.replay_ok === false) setReplayError(result.clock.replay_error || null);
    else onOpenTrader(symbol);
  };
  const failure = errors.replay ?? replayError;
  // ADR 039: Records holds the Session Records and the video clips; a link can ask for the clips.
  const { view: clipsView, version: clipsVersion } = useClips();
  const [tab, setTab] = useState<'sessions' | 'clips'>(() => (takeClipsListRequest() ? 'clips' : 'sessions'));
  // A link that asks for the clips while Records is already open (the request bumps the version).
  useEffect(() => {
    if (takeClipsListRequest()) setTab('clips');
  }, [clipsVersion]);

  return (
    <div className="nova-shell nova-shell--scanner">
      <div className="main-col main-col--scanner-stack">
        <section className="panel rail-page records-page" aria-label={RECORDS_PAGE_TITLE} data-testid="records-page">
          <div className="records-head">
            <h2 className="rail-page__title">{RECORDS_PAGE_TITLE}</h2>
            <div className="records-head__tabs" role="tablist" aria-label={RECORDS_PAGE_TITLE}>
              <button type="button" role="tab" aria-selected={tab === 'sessions'} className={tab === 'sessions' ? 'is-on' : undefined}
                data-testid="records-tab-sessions" onClick={() => setTab('sessions')}>
                {CLIP_RECORDS_TAB_SESSIONS}<b>{sessionCount}</b>
              </button>
              <button type="button" role="tab" aria-selected={tab === 'clips'} className={tab === 'clips' ? 'is-on' : undefined}
                data-testid="records-tab-clips" onClick={() => setTab('clips')}>
                {CLIP_RECORDS_TAB_CLIPS}<b>{clipsView?.clips.length ?? 0}</b>
              </button>
            </div>
            {tab === 'sessions' && data?.root && <span className="records-head__where">{recordsSavedTo(data.root)}</span>}
          </div>
          {tab === 'clips' ? <ClipsList onOpenTrader={onOpenTrader} /> : (<>
            <div className="records-top">
              <RecordingNowCard status={status} symbols={recordingSymbols} todayRows={todayRows} nowMs={nowMs}
                onOpenTrader={onOpenTrader} control={control} />
              <AutoRecordCard auto={status.auto_record} nowSec={nowMs / 1000} control={control} />
            </div>
            {failure && (
              <p className="rail-page__note" role="alert" data-testid="records-page-replay-error">
                {RECORDS_PAGE_REPLAY_FAILED} {failure}
              </p>
            )}
            {error && !data ? (
              <p className="rail-page__note" role="alert">{RECORDS_PAGE_ERROR_PREFIX} {error}</p>
            ) : !data ? (
              <p className="rail-page__note">{RECORDS_PAGE_LOADING}</p>
            ) : days.length === 0 ? (
              <p className="rail-page__note" data-testid="records-page-empty">{RECORDS_PAGE_EMPTY}</p>
            ) : (<>
              {error && <p className="rail-page__note" role="alert">{RECORDS_PAGE_ERROR_PREFIX} {error}</p>}
              <RecordsDayTable byDay={byDay} recording={recording} today={today} nowSec={nowMs / 1000} sim={sim}
                replayBusy={busy.has('replay')} onReplay={(date, symbol) => void replay(date, symbol)}
                onOpenTrader={onOpenTrader} />
            </>)}
          </>)}
        </section>
      </div>
    </div>
  );
}
