/**
 * Share clips' toasts (ADR 039, mockup v1 board 3): a stopped clip and a
 * saved "last 5 min" offer the export (Later keeps it in Records), and a
 * finished or failed export says so with Show in folder / Play or the reason.
 * One toast per clip; each leaves after CLIP_TOAST_TTL_MS unless pointed at.
 * Mounted once in the main desk's header.
 */
import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { History, Video, X } from 'lucide-react';
import { bytesLabel, clockLabel, etClock, sourcesWords } from './clipModel';
import {
  CLIP_EXPORT_ACTION,
  CLIP_LATER,
  CLIP_PLAY,
  CLIP_SHOW_IN_FOLDER,
  CLIP_TOAST_EXPORTED,
  CLIP_TOAST_EXPORT_FAILED,
  CLIP_TOAST_LAST,
  CLIP_TOAST_REGION,
  CLIP_TOAST_SAVED,
  CLIP_TOAST_TTL_MS,
} from './clipsConstants';
import {
  actClip,
  dismissClipToast,
  getClipsVersion,
  getClipToasts,
  openClipExport,
  pushClipToast,
  subscribeClips,
  useClips,
  type ClipToast as Toast,
} from './clipsStore';
import type { ClipRowView } from './clipsView';

const TITLES: Record<Toast['kind'], string> = {
  saved: CLIP_TOAST_SAVED,
  last: CLIP_TOAST_LAST,
  exported: CLIP_TOAST_EXPORTED,
  failed: CLIP_TOAST_EXPORT_FAILED,
};

function body(row: ClipRowView | null, toast: Toast): string {
  if (!row) return toast.text;
  const range = `${row.symbol} ${etClock(row.startedTs)} – ${row.endedTs ? etClock(row.endedTs) : 'now'} ET (${clockLabel(row.lengthSec)})`;
  if (toast.kind === 'failed') return `${range}. ${row.export?.error ?? 'The export failed.'}`;
  if (toast.kind === 'exported') return `${range} · ${bytesLabel(row.export?.bytes ?? null)}`;
  const hidden = row.hiddenSec > 0 ? ` The tab showed something else for ${clockLabel(row.hiddenSec)} (marked).` : '';
  const gap = row.gapSec > 0 ? ` Nova was down for ${clockLabel(row.gapSec)} (left out).` : '';
  if (toast.kind === 'last') return `${range}, cut from the screen recording. Move the start earlier at export: the whole day is there.`;
  return `${range}. ${sourcesWords(row)}.${hidden}${gap}`;
}

function ClipToastCard({ toast, row }: { toast: Toast; row: ClipRowView | null }) {
  const [hover, setHover] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (hover) return undefined;
    const id = window.setTimeout(() => dismissClipToast(toast.id), CLIP_TOAST_TTL_MS);
    return () => window.clearTimeout(id);
  }, [hover, toast.id]);
  const act = async (action: 'show' | 'play') => {
    const res = await actClip({ action, clip_id: toast.clipId });
    if (!res.ok) setError(res.error ?? 'That did not work.');
  };
  const done = toast.kind === 'exported';
  return (
    <div className={`clip-toast clip-toast--${toast.kind}`} role="status" data-testid="clip-toast" data-kind={toast.kind}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <span className="clip-toast__icon" aria-hidden="true">{toast.kind === 'last' ? <History size={14} /> : <Video size={14} />}</span>
      <div className="clip-toast__text">
        <div className="clip-toast__head">
          <strong>{TITLES[toast.kind]}{toast.kind === 'saved' && row ? ` · ${row.symbol} ${clockLabel(row.lengthSec)}` : ''}</strong>
        </div>
        <span className="clip-toast__body">{body(row, toast)}</span>
        {error ? <span className="clip-toast__error">{error}</span> : null}
        <div className="clip-toast__actions">
          {done ? (
            <>
              <button type="button" className="clip-btn clip-btn--sm" onClick={() => void act('show')}>{CLIP_SHOW_IN_FOLDER}</button>
              <button type="button" className="clip-btn clip-btn--sm" onClick={() => void act('play')}>{CLIP_PLAY}</button>
            </>
          ) : (
            <>
              <button type="button" className="clip-btn clip-btn--pri clip-btn--sm" data-testid="clip-toast-export"
                onClick={() => { openClipExport(toast.clipId); dismissClipToast(toast.id); }}>
                {CLIP_EXPORT_ACTION}
              </button>
              <button type="button" className="clip-btn clip-btn--sm" onClick={() => dismissClipToast(toast.id)}>{CLIP_LATER}</button>
            </>
          )}
        </div>
      </div>
      <button type="button" className="clip-toast__dismiss" aria-label="Dismiss" onClick={() => dismissClipToast(toast.id)}>
        <X size={13} aria-hidden="true" />
      </button>
    </div>
  );
}

export function ClipToasts() {
  const { view } = useClips();
  useSyncExternalStore(subscribeClips, getClipsVersion, () => 0);
  const toasts = getClipToasts();
  const seen = useRef<Map<string, string>>(new Map());

  // An export this window watched finish (or fail) is said once.
  useEffect(() => {
    if (!view) return;
    const was = seen.current;
    for (const row of view.clips) {
      const before = was.get(row.clipId);
      if ((before === 'exporting' || before === 'queued') && (row.status === 'ready' || row.status === 'failed')) {
        pushClipToast({ kind: row.status === 'ready' ? 'exported' : 'failed', clipId: row.clipId, clip: null, text: row.symbol });
      }
      was.set(row.clipId, row.status);
    }
  }, [view]);

  if (!toasts.length) return null;
  const rows = new Map((view?.clips ?? []).map((r) => [r.clipId, r]));
  return (
    <div className="clip-toasts" role="region" aria-label={CLIP_TOAST_REGION} data-testid="clip-toasts">
      {toasts.map((t) => <ClipToastCard key={t.id} toast={t} row={rows.get(t.clipId) ?? null} />)}
    </div>
  );
}
