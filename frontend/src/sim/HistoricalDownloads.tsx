import { etTime } from './historicalReplayFormat';
import {
  durationLabel, importContentsLabel, importStagesLabel, jobLabel, jobSummary, nothingDownloaded, progressPercent,
} from './historicalProgress';
import {
  SIM_HISTORY_NOTHING_DOWNLOADED_LINE, SIM_MASSIVE_IMPORT_NOTHING_YET, SIM_WHY_JOB_PAUSING, simWhyJobBusy,
} from './simConstants';
import { isMassive, type HistoricalJob } from './historicalTypes';

/** "12,345" / "--": a job count the payload did not carry is unknown, never a crash (C7). */
const countLabel = (value: number | null | undefined): string =>
  value != null && Number.isFinite(value) ? value.toLocaleString() : '--';

type JobAction = (job: HistoricalJob, action: 'pause' | 'resume') => void;

/**
 * An import from the Massive files (ADR 046): read from disk in one go, so no
 * pages and no "downloaded through" -- each file's share read while it runs,
 * what it holds once done. Stop ends it; Import again reads the window afresh.
 */
function MassiveImport({ job, busy, onPick, onAction }: {
  job: HistoricalJob; busy: Set<string>; onPick: (job: HistoricalJob) => void; onAction: JobAction;
}) {
  const percent = progressPercent(job);
  const running = job.status === 'running' && !job.stale;
  const label = running ? 'Stop import' : 'Import again';
  const stages = running ? importStagesLabel(job) : null;
  return <li aria-label={jobLabel(job)} className="sim-download" data-source="massive">
    <strong>{job.symbol}  -  {job.date}  -  {job.start} - {job.end}</strong>
    <div role="status" aria-live="polite">{jobSummary(job)}  -  Massive files{job.status === 'complete' ? `: ${importContentsLabel(job)}` : ''}</div>
    {running && percent != null && <progress aria-label={`Import progress: ${jobLabel(job)}`} value={percent} max={100} />}
    <div className="sim-muted">
      {stages && <>Reading {stages}. </>}
      {running && <>{SIM_MASSIVE_IMPORT_NOTHING_YET} </>}
      {job.started != null && job.updated != null && <>Elapsed {durationLabel(Math.max(0, job.updated - job.started))}. </>}
      {running && job.eta_seconds != null && <>Estimated {durationLabel(job.eta_seconds)} remaining.</>}
    </div>
    <div className="sim-actions">
      <button type="button" aria-label={`Use this window: ${jobLabel(job)}`} onClick={() => onPick(job)}>Use this window</button>
      {job.status !== 'complete' && <button type="button" disabled={busy.has(job.id)}
        data-why={busy.has(job.id) ? simWhyJobBusy(label) : undefined}
        aria-label={`${label}: ${jobLabel(job)}`}
        onClick={() => onAction(job, running ? 'pause' : 'resume')}>{label}</button>}
    </div>
    {job.error && <p role="alert" className="sim-error">{job.error}</p>}
  </li>;
}

export function HistoricalDownloads({ jobs, busy, onPick, onAction }: {
  jobs: HistoricalJob[]; busy: Set<string>; onPick: (job: HistoricalJob) => void; onAction: JobAction;
}) {
  return <ul aria-label="Historical downloads" className="sim-downloads">{jobs.map(job => {
    if (isMassive(job)) return <MassiveImport key={job.id} job={job} busy={busy} onPick={onPick} onAction={onAction} />;
    const percent = progressPercent(job);
    const through = job.downloaded_through ?? job.cursor;
    // Nothing covered: "through the window start" would read as progress (C45).
    const empty = nothingDownloaded(job.covered_seconds);
    const action = job.status === 'running' && !job.stale ? 'pause' : 'resume';
    // A failed job starts again from its checkpoint: a retry, not a resume (R28).
    const actionLabel = action === 'pause' ? 'Pause download' : job.status === 'failed' ? 'Retry download' : 'Resume download';
    return <li key={job.id} aria-label={jobLabel(job)} className="sim-download">
      <strong>{job.symbol}  -  {job.date}  -  {job.start} - {job.end}</strong>
      <div role="status" aria-live="polite">{jobSummary(job)}  -  {job.kind}: {countLabel(job.count)} {job.kind === 'trades' ? 'prints' : 'candles'}  -  {countLabel(job.pages)} pages</div>
      {percent != null && <progress aria-label={`Download progress: ${jobLabel(job)}`} value={percent} max={100} />}
      <div className="sim-muted">
        {empty ? <>{SIM_HISTORY_NOTHING_DOWNLOADED_LINE} </> : through != null && <>Downloaded through {etTime(through)} ET. </>}
        {job.started != null && job.updated != null && <>Elapsed {durationLabel(Math.max(0, job.updated - job.started))}. </>}
        {job.eta_seconds != null ? <>Estimated {durationLabel(job.eta_seconds)} remaining.</> : job.status === 'running' && !job.stale ? 'ETA available after progress advances.' : null}
        {job.stale && <> No checkpoint{job.age_seconds != null ? ` for ${durationLabel(job.age_seconds)}` : ''}. Resume to retry.</>}
      </div>
      <div className="sim-actions">
        <button type="button" aria-label={`Use this window: ${jobLabel(job)}`} onClick={() => onPick(job)}>Use this window</button>
        {job.status === 'pause_requested' && !job.stale
          ? <button type="button" disabled data-why={SIM_WHY_JOB_PAUSING} aria-label={`Pausing download: ${jobLabel(job)}`}>Pausing - </button>
          : job.status !== 'complete' && <button type="button" disabled={busy.has(job.id)}
            data-why={busy.has(job.id) ? simWhyJobBusy(actionLabel) : undefined}
            aria-label={`${actionLabel}: ${jobLabel(job)}`}
            onClick={() => onAction(job, action)}>{actionLabel}</button>}
      </div>
      {job.error && <p role="alert" className="sim-error">{job.error}</p>}
    </li>;
  })}</ul>;
}
