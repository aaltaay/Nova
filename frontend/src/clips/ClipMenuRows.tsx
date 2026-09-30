/**
 * The symbol menu's video rows (ADR 039): right-click any ticker for the
 * same choices as the red ● -- a video clip of its Trader tab (start or stop)
 * and Save the last 5 min. The rows look like the menu's own (symbolMenu.css);
 * a locked row says why, and a refused request shows the reason under it.
 */
import { useEffect, useState } from 'react';
import { History, Square, TriangleAlert, Video } from 'lucide-react';
import { clockLabel, openClipFor, videoMenuState } from './clipModel';
import { actClip, pushClipToast, useClips } from './clipsStore';

const ICON_PX = 15;

export function ClipMenuRows({ symbol, onDone }: { symbol: string; onDone: () => void }) {
  const { desktop, view } = useClips();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now() / 1000);
  const open = openClipFor(view, symbol);
  useEffect(() => {
    if (!open) return undefined;
    const id = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(id);
  }, [open]);
  const vs = videoMenuState({ desktop, view, symbol, busy });

  const run = async (request: Record<string, unknown>, toast: 'saved' | 'last' | null) => {
    setBusy(true);
    setError(null);
    const res = await actClip(request);
    setBusy(false);
    if (!res.ok) {
      setError(res.error ?? 'That did not work.');
      return;
    }
    const clipId = String((res.clip as { clip_id?: string } | undefined)?.clip_id ?? res.clip_id ?? '');
    if (toast && clipId) pushClipToast({ kind: toast, clipId, clip: null, text: symbol });
    onDone();
  };

  return (
    <>
      <button
        type="button"
        role="menuitem"
        className={`symbol-menu__row symbol-menu__row--rec${open ? ' is-on' : ''}`}
        data-testid="bot-symbol-menu-clip"
        disabled={open ? busy : !vs.canStart}
        data-why={open ? (busy ? 'Working on it…' : undefined) : vs.startWhy ?? undefined}
        onClick={() => void (open ? run({ action: 'stop', clip_id: open.clipId }, 'saved') : run({ action: 'start', symbol, origin: 'symbol_menu' }, null))}
      >
        <span className="symbol-menu__icon symbol-menu__icon--rec" aria-hidden="true">
          {open ? <Square size={ICON_PX - 3} fill="currentColor" /> : <Video size={ICON_PX} />}
        </span>
        <span className="symbol-menu__text">
          <span className="symbol-menu__label">{open ? 'Stop the video clip' : 'Record a video clip'}</span>
          <span className="symbol-menu__hint">{open ? 'saves it; the export opens from the toast' : `a cut of ${symbol}'s Trader tab from the screen recording`}</span>
        </span>
        {open ? <span className="symbol-menu__state symbol-menu__state--rec">{clockLabel(now - open.startedTs)}</span> : null}
      </button>
      <button
        type="button"
        role="menuitem"
        className="symbol-menu__row symbol-menu__row--rec"
        data-testid="bot-symbol-menu-clip-last"
        disabled={!desktop || !view || busy}
        data-why={!desktop ? 'Video clips need the desktop app' : !view ? 'The desktop app has not answered yet' : busy ? 'Working on it…' : undefined}
        onClick={() => void run({ action: 'save_last', symbol, seconds: view?.lastNSec }, 'last')}
      >
        <span className="symbol-menu__icon symbol-menu__icon--rec" aria-hidden="true"><History size={ICON_PX} /></span>
        <span className="symbol-menu__text">
          <span className="symbol-menu__label">Save the last 5 min</span>
          <span className="symbol-menu__hint">{`of ${symbol}'s Trader tab, as a clip that ends now`}</span>
        </span>
      </button>
      {error ? (
        <div className="symbol-menu__error" role="alert">
          <TriangleAlert size={13} aria-hidden="true" />
          <span>{error}</span>
        </div>
      ) : null}
    </>
  );
}
