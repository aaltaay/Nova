import { etTime } from './historicalReplayFormat';
import { durationLabel, jobLabel, jobSummary, nothingDownloaded, progressPercent } from './historicalProgress';
import { SIM_HISTORY_NOTHING_DOWNLOADED_LINE } from './simConstants';
import type { HistoricalJob } from './historicalTypes';

/** "12,345" / "--": a job count the payload did not carry is unknown, never a crash (C7). */
const countLabel = (value: number | null | undefined): string =>
  value != null && Number.isFinite(value) ? value.toLocaleString() : '--';

export function HistoricalDownloads({ jobs, busy, onPick, onAction }: {
  jobs: HistoricalJob[]; busy: Set<string>; onPick: (job: HistoricalJob) => void;
  onAction: (job: HistoricalJob, action: 'pause' | 'resume') => void;
}) {
  return <ul aria-label="Historical downloads" className="sim-downloads">{jobs.map(job => {
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
          ? <button type="button" disabled aria-label={`Pausing download: ${jobLabel(job)}`}>Pausing - </button>
          : job.status !== 'complete' && <button type="button" disabled={busy.has(job.id)}
            aria-label={`${actionLabel}: ${jobLabel(job)}`}
            onClick={() => onAction(job, action)}>{actionLabel}</button>}
      </div>
      {job.error && <p role="alert" className="sim-error">{job.error}</p>}
    </li>;
  })}</ul>;
}
