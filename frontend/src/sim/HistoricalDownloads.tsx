import { etTime } from './historicalReplayFormat';
import { durationLabel, jobLabel, jobSummary, progressPercent } from './historicalProgress';
import type { HistoricalJob } from './historicalTypes';

export function HistoricalDownloads({ jobs, busy, onPick, onAction }: {
  jobs: HistoricalJob[]; busy: Set<string>; onPick: (job: HistoricalJob) => void;
  onAction: (job: HistoricalJob, action: 'pause' | 'resume') => void;
}) {
  return <ul aria-label="Historical downloads" className="sim-downloads">{jobs.map(job => {
    const percent = progressPercent(job);
    const through = job.downloaded_through ?? job.cursor;
    const action = job.status === 'running' && !job.stale ? 'pause' : 'resume';
    return <li key={job.id} aria-label={jobLabel(job)} className="sim-download">
      <strong>{job.symbol}  -  {job.date}  -  {job.start} - {job.end}</strong>
      <div role="status" aria-live="polite">{jobSummary(job)}  -  {job.kind}: {job.count.toLocaleString()} {job.kind === 'trades' ? 'prints' : 'candles'}  -  {job.pages} pages</div>
      {percent != null && <progress aria-label={`Download progress: ${jobLabel(job)}`} value={percent} max={100} />}
      <div className="sim-muted">
        {through != null && <>Downloaded through {etTime(through)} ET. </>}
        {job.started != null && job.updated != null && <>Elapsed {durationLabel(Math.max(0, job.updated - job.started))}. </>}
        {job.eta_seconds != null ? <>Estimated {durationLabel(job.eta_seconds)} remaining.</> : job.status === 'running' && !job.stale ? 'ETA available after progress advances.' : null}
        {job.stale && <> No checkpoint{job.age_seconds != null ? ` for ${durationLabel(job.age_seconds)}` : ''}. Resume to retry.</>}
      </div>
      <div className="sim-actions">
        <button type="button" aria-label={`Use this window: ${jobLabel(job)}`} onClick={() => onPick(job)}>Use this window</button>
        {job.status === 'pause_requested' && !job.stale
          ? <button type="button" disabled aria-label={`Pausing download: ${jobLabel(job)}`}>Pausing - </button>
          : job.status !== 'complete' && <button type="button" disabled={busy.has(job.id)}
            aria-label={`${action === 'pause' ? 'Pause' : 'Resume'} download: ${jobLabel(job)}`}
            onClick={() => onAction(job, action)}>{action === 'pause' ? 'Pause download' : 'Resume download'}</button>}
      </div>
      {job.error && <p role="alert" className="sim-error">{job.error}</p>}
    </li>;
  })}</ul>;
}
