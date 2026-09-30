/**
 * Records › Video clips (ADR 039, mockup v1 board 5): every clip, newest day
 * first, on the Records page beside Session Records. What records now has its
 * Stop; a clip is marks until it is exported (no disk of its own); each row's
 * actions follow its state; a failure says why and keeps the clip; a picture
 * that shows the header says so. Delete asks first and removes the clip's own
 * files only -- never the screen recording.
 */
import { useEffect, useState } from 'react';
import { confirmApp } from '../ux';
import { bytesLabel, clockLabel, etClock, etDate, pictureWords, sourcesWords, statusWords } from './clipModel';
import {
  CLIP_CANCEL,
  CLIP_DELETE,
  CLIP_EXPORT_ACTION,
  CLIP_EXPORT_AGAIN,
  CLIP_NEED_DESKTOP,
  CLIP_OPEN_TRADER,
  CLIP_PLAY,
  CLIP_RECORDS_EMPTY,
  CLIP_RECORDS_KEPT,
  CLIP_RETRY,
  CLIP_SHOW_IN_FOLDER,
  CLIP_STOP,
} from './clipsConstants';
import { actClip, openClipExport, pushClipToast, useClips } from './clipsStore';
import type { ClipRowView } from './clipsView';

function Row({ row, now, onOpenTrader, onError }: { row: ClipRowView; now: number; onOpenTrader: (s: string) => void; onError: (e: string | null) => void }) {
  const [busy, setBusy] = useState(false);
  const status = statusWords(row);
  const picture = pictureWords(row);
  const act = async (request: Record<string, unknown>) => {
    setBusy(true);
    const res = await actClip(request);
    setBusy(false);
    onError(res.ok ? null : res.error ?? 'That did not work.');
    return res;
  };
  const remove = async () => {
    const ok = await confirmApp({
      title: `Delete this ${row.symbol} clip?`,
      message: `${row.export?.file ? `Deletes ${row.export.file} (${bytesLabel(row.export.bytes)}) and any high-quality file of it.` : 'Deletes its high-quality file, if any.'} The screen recording it came from stays.`,
      confirmLabel: CLIP_DELETE,
      tone: 'danger',
    });
    if (ok) await act({ action: 'delete', clip_id: row.clipId });
  };
  const length = row.status === 'recording' ? `${clockLabel(now - row.startedTs)} so far` : clockLabel(row.lengthSec);
  const btn = (label: string, fn: () => void, extra = '') => (
    <button type="button" className={`records-page__open${extra}`} disabled={busy} data-why={busy ? 'Working on it…' : undefined} onClick={fn}>{label}</button>
  );
  return (
    <tr data-testid="clip-row" data-status={row.status}>
      <td>{etClock(row.startedTs)} – {row.endedTs ? etClock(row.endedTs) : 'now'}</td>
      <td>{row.symbol}</td>
      <td className="is-num">{length}</td>
      <td>{picture.text}{picture.warn ? <span className="clip-warn-text"> · {picture.warn}</span> : null}</td>
      <td>{row.status === 'recording' ? (row.hqSec > 0 ? 'High quality · 30 fps' : 'Cut · 15 fps') : sourcesWords(row)}</td>
      <td className="is-num">{row.status === 'ready' ? bytesLabel(row.export?.bytes ?? null) : '—'}</td>
      <td><span className={`clip-status clip-status--${status.tone}`}>{status.tone === 'rec' ? <i aria-hidden="true" /> : null}{status.text}</span></td>
      <td className="clip-list__actions">
        {row.status === 'recording' ? (
          <>
            {btn(CLIP_STOP, () => void act({ action: 'stop', clip_id: row.clipId }).then((res) => res.ok && pushClipToast({ kind: 'saved', clipId: row.clipId, clip: null, text: row.symbol })), ' clip-btn--danger-outline')}
            {btn(CLIP_OPEN_TRADER, () => onOpenTrader(row.symbol))}
          </>
        ) : row.status === 'exporting' || row.status === 'queued' ? (
          btn(CLIP_CANCEL, () => row.export && void act({ action: 'cancel_export', export_id: row.export.exportId }))
        ) : row.status === 'ready' ? (
          <>
            {btn(CLIP_PLAY, () => void act({ action: 'play', clip_id: row.clipId }))}
            {btn(CLIP_SHOW_IN_FOLDER, () => void act({ action: 'show', clip_id: row.clipId }))}
            {btn(CLIP_EXPORT_AGAIN, () => openClipExport(row.clipId))}
            {btn(CLIP_DELETE, () => void remove())}
          </>
        ) : (
          <>
            {btn(row.status === 'failed' ? CLIP_RETRY : CLIP_EXPORT_ACTION, () => openClipExport(row.clipId))}
            {btn(CLIP_DELETE, () => void remove())}
          </>
        )}
      </td>
    </tr>
  );
}

export function ClipsList({ onOpenTrader }: { onOpenTrader: (symbol: string) => void }) {
  const { desktop, view } = useClips();
  const [now, setNow] = useState(() => Date.now() / 1000);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(id);
  }, []);
  if (!desktop) return <p className="rail-page__note" data-testid="clips-no-desktop">{CLIP_NEED_DESKTOP}</p>;
  if (!view) return <p className="rail-page__note">Reading the clip list…</p>;
  const days = new Map<string, ClipRowView[]>();
  for (const row of view.clips) {
    const d = etDate(row.startedTs);
    days.set(d, [...(days.get(d) ?? []), row]);
  }
  const total = view.clips.reduce((t, r) => t + (r.status === 'ready' ? r.export?.bytes ?? 0 : 0), 0);
  const today = etDate(now);
  return (
    <div className="clip-list" data-testid="clips-list">
      <p className="rail-page__sub">
        Clips cut from the screen recording, newest day first · {view.dir} · {view.clips.length} clip{view.clips.length === 1 ? '' : 's'} · {bytesLabel(total)}
        {view.disk.freeBytes !== null ? ` · ${view.dir.slice(0, 2)} ${bytesLabel(view.disk.freeBytes)} free` : ''}. {CLIP_RECORDS_KEPT}
      </p>
      {view.dirError ? <p className="rail-page__note" role="alert">{view.dirError}</p> : null}
      {view.open.length ? (
        <p className="records-page__recording" data-testid="clips-recording-now">
          Recording now:{' '}
          {view.open.map((o) => `${o.symbol} ${clockLabel(now - o.startedTs)}${o.hq ? ` (high quality${o.hq.endsAt ? `, ${clockLabel(o.hq.endsAt - now)} left` : ''})` : ''}`).join(' · ')}
        </p>
      ) : null}
      {error ? <p className="rail-page__note" role="alert">{error}</p> : null}
      {!view.clips.length ? <p className="rail-page__note" data-testid="clips-empty">{CLIP_RECORDS_EMPTY}</p> : null}
      {[...days].map(([day, rows]) => (
        <div key={day}>
          <h3 className="rail-page__sub">{day}{day === today ? ' · today' : ''}</h3>
          <table className="records-page__table clip-list__table">
            <colgroup>
              <col style={{ width: '13%' }} /><col style={{ width: '6%' }} /><col style={{ width: '8%' }} /><col style={{ width: '17%' }} />
              <col style={{ width: '14%' }} /><col style={{ width: '6%' }} /><col style={{ width: '15%' }} /><col />
            </colgroup>
            <thead>
              <tr><th>Time (ET)</th><th>Symbol</th><th className="is-num">Length</th><th>Picture</th><th>Frames</th><th className="is-num">Size</th><th>Status</th><th /></tr>
            </thead>
            <tbody>
              {rows.map((row) => <Row key={row.clipId} row={row} now={now} onOpenTrader={onOpenTrader} onError={setError} />)}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
