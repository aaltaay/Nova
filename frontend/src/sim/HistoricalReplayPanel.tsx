import { useRef, useState } from 'react';
import { Popover } from 'radix-ui';
import { useWorkspace } from '../workspace';
import { etTime, previousEtWeekday } from './historicalReplayFormat';
import { SIM_HISTORY_LARGE_WINDOW_MINUTES, SIM_HISTORY_PAGE_INTERVAL_SEC, SIM_SESSION_CLOSE_LABEL, SIM_SESSION_OPEN_LABEL } from './simConstants';
import { useHistoricalStatus, historicalStatus } from './historicalStatusStore';
import { useReplayActions } from './useReplayActions';
import { selectHistoricalReplay } from './historicalReplayLoad';
import { HistoricalDownloads } from './HistoricalDownloads';
import { durationLabel, jobSummary, validateHistoricalWindow, windowLabel, windowMinutes } from './historicalProgress';
import type { HistoricalJob, HistoricalWindow } from './historicalTypes';

export function HistoricalReplayPanel() {
  const { openStockView } = useWorkspace();
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const anchor = useRef({ getBoundingClientRect: () =>
    (trigger.current?.closest('.sim-session-header') ?? trigger.current)?.getBoundingClientRect() ?? new DOMRect() });
  const [symbol, setSymbol] = useState('');
  const [date, setDate] = useState<string | null>(null);
  const [start, setStart] = useState(SIM_SESSION_OPEN_LABEL);
  const [end, setEnd] = useState(SIM_SESSION_CLOSE_LABEL);
  const [formError, setFormError] = useState('');
  const status = useHistoricalStatus(open);
  const { request, busy, errors } = useReplayActions();
  const jobs = Array.isArray(status.data?.jobs) ? status.data.jobs : [];
  const selection = status.data?.selection;
  const spec: HistoricalWindow = { symbol: symbol.trim().toUpperCase(), date: date ?? status.data?.default_date ?? previousEtWeekday(), start, end };
  const primary = jobs.find(job => !job.stale && ['running', 'pause_requested'].includes(job.status))
    ?? jobs.find(job => ['running', 'pause_requested'].includes(job.status))
    ?? jobs.find(job => job.stale || job.error) ?? jobs[0];
  const validate = () => { const message = validateHistoricalWindow(spec); setFormError(message ?? ''); return !message; };
  const update = (setter: (value: string) => void, value: string) => { setter(value); setFormError(''); };
  async function load() {
    if (!validate()) return;
    if (!await selectHistoricalReplay(request, spec)) return;
    openStockView(spec.symbol);
    setOpen(false);
  }
  async function download(kind: 'bars' | 'trades') {
    if (!validate()) return;
    if (await request(`download:${kind}`, '/history', { ...spec, kind })) void historicalStatus.refresh();
  }
  const pick = (job: HistoricalJob) => { setSymbol(job.symbol); setDate(job.date); setStart(job.start); setEnd(job.end); setFormError(''); };
  const action = async (job: HistoricalJob, operation: 'pause' | 'resume') => {
    if (await request(job.id, `/history/${encodeURIComponent(job.id)}/${operation}`)) void historicalStatus.refresh();
  };
  const selectionLabel = selection && `${windowLabel(selection)}  -  ${selection.trade_count?.toLocaleString() ?? 'Unknown'} downloaded prints`;
  return <div className="sim-history">
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Anchor virtualRef={anchor} />
      <Popover.Trigger asChild><button ref={trigger} type="button" className="sim-history__trigger">Historical replay</button></Popover.Trigger>
      <Popover.Portal>
        <Popover.Content side="bottom" align="end" sideOffset={12} collisionPadding={12}
          sticky="always" className="sim-history__panel" aria-label="Historical replay setup">
          <div className="sim-history__title"><strong>Historical replay</strong><Popover.Close asChild><button type="button" aria-label="Close historical replay">Close</button></Popover.Close></div>
          <p>Replay any supported stock ticker. Times are America/New_York.</p>
          <div className="sim-history__fields">
            <label>Ticker <input aria-label="Historical ticker" value={symbol} onChange={event => update(setSymbol, event.target.value.toUpperCase())} size={8} /></label>
            <label>Date <input type="date" value={spec.date} onChange={event => update(setDate, event.target.value)} /></label>
            <label>From <input type="time" value={start} onChange={event => update(setStart, event.target.value)} /></label>
            <label>To <input type="time" value={end} onChange={event => update(setEnd, event.target.value)} /></label>
          </div>
          <p className="sim-actions">
            <button type="button" disabled={busy.has('select') || !spec.symbol} onClick={() => void load()}>Load replay</button>
            <button type="button" disabled={busy.has('download:bars') || !spec.symbol} onClick={() => void download('bars')}>Download candles</button>
            <button type="button" disabled={busy.has('download:trades') || !spec.symbol} onClick={() => void download('trades')}>Download trades</button>
          </p>
          <p className="sim-muted">{windowMinutes(spec) >= SIM_HISTORY_LARGE_WINDOW_MINUTES && <strong>Large window ({(windowMinutes(spec) / 60).toFixed(1)} hours). </strong>}Trades are paced at least {SIM_HISTORY_PAGE_INTERVAL_SEC} seconds per page and can take many minutes. ETA starts after the first advancing checkpoint; choose a shorter window for a faster download.</p>
          <p className="sim-muted">Load any time: a window loaded mid-download picks up new prints by itself, and the playhead stays put. Candles appear at interval close. Historical quotes and Level 2 are unavailable.</p>
          {formError && <p role="alert" className="sim-error">{formError}</p>}
          {Object.entries(errors).map(([key, message]) => <p key={key} role="alert" className="sim-error">{message}</p>)}
          <HistoricalDownloads jobs={jobs} busy={busy} onPick={pick} onAction={(job, operation) => void action(job, operation)} />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
    <span role="status" className="sim-history__summary" title={primary ? `${primary.symbol} ${primary.date} ${primary.start} - ${primary.end}` : undefined}>
      {status.error ? `Download status unavailable: ${status.error}` : primary ? `${jobSummary(primary)}${primary.eta_seconds != null ? ` - about ${durationLabel(primary.eta_seconds)} remaining` : ''}` : ''}
    </span>
    {selection && <span role="status" className="sim-history__selection" title={selectionLabel ?? undefined}>
      Selected: {selectionLabel}. {selection.download_status === 'missing'
        ? 'No downloaded trades for this window; candles appear only if stored.'
        : <>Trades through {etTime(selection.coverage_through)} ET  -  {selection.download_status ?? 'coverage unknown'}.</>}
    </span>}
  </div>;
}
