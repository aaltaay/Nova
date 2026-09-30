/**
 * The header's CLIP chips (ADR 039, mockup v1 board 2): one per open clip,
 * beside the REC chips, counting up. Its look says what is going on -- High
 * quality's last minute (amber, counting down), a hidden tab (dimmed), a lost
 * capture (amber), no picture at all (red, the one loud state). Pointing at a
 * chip shows its card and has the tab it films draw its red frame; a click
 * stops the clip and offers the export.
 */
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Video } from 'lucide-react';
import { chipModel, clockLabel } from './clipModel';
import { CLIP_ROLE } from './clipsConstants';
import { actClip, pushClipToast, setHoveredClip, useClips } from './clipsStore';
import type { ClipRowView, OpenClip } from './clipsView';

function ClipChip({ clip, nowSec, warnSec }: { clip: OpenClip; nowSec: number; warnSec: number }) {
  const m = chipModel(clip, nowSec, warnSec);
  const [card, setCard] = useState<{ left: number; top: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const stop = async () => {
    setBusy(true);
    const res = await actClip({ action: 'stop', clip_id: clip.clipId });
    setBusy(false);
    if (!res.ok) {
      setError(res.error ?? 'The clip did not stop.');
      return;
    }
    const row = res.clip as ClipRowView | undefined;
    setHoveredClip(null);
    pushClipToast({ kind: 'saved', clipId: clip.clipId, clip: null, text: `${clip.symbol} ${clockLabel(row?.lengthSec ?? nowSec - clip.startedTs)}` });
  };

  return (
    <>
      <button
        type="button"
        className={`global-app-bar__rec clip-chip clip-chip--${m.tone}`}
        data-testid="clip-chip"
        data-symbol={clip.symbol}
        data-state={clip.state}
        aria-label={`${CLIP_ROLE} ${clip.symbol} ${m.time}${m.extra ? ` ${m.extra}` : ''}`}
        disabled={busy}
        data-why={busy ? 'Stopping…' : undefined}
        onMouseEnter={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          setCard({ left: r.left, top: r.bottom + 8 });
          setHoveredClip(clip.clipId);
        }}
        onMouseLeave={() => {
          setCard(null);
          setHoveredClip(null);
        }}
        onClick={() => void stop()}
      >
        <Video size={12} className="clip-chip__icon" aria-hidden="true" />
        <span className="global-app-bar__rec-role">{CLIP_ROLE}</span>
        <span className="global-app-bar__rec-symbol">{clip.symbol}</span>
        <span className="global-app-bar__rec-time">{m.time}</span>
        {m.hq ? <span className="clip-chip__hq">HQ</span> : null}
        {m.extra ? <span className="clip-chip__extra">{m.extra}</span> : null}
      </button>
      {card
        ? createPortal(
            <div className="clip-card" role="tooltip" data-testid="clip-card" style={{ left: card.left, top: card.top }}>
              {m.lines.map((line, i) => (
                <div key={i} className={i === 0 ? 'clip-card__head' : i === m.lines.length - 1 ? 'clip-card__foot' : undefined}>{line}</div>
              ))}
              {error ? <div className="clip-card__error">{error}</div> : null}
            </div>,
            document.body,
          )
        : null}
    </>
  );
}

export function ClipChips() {
  const { view } = useClips();
  const [now, setNow] = useState(() => Date.now() / 1000);
  const count = view?.open.length ?? 0;
  useEffect(() => {
    if (!count) return undefined;
    const id = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(id);
  }, [count]);
  if (!view || !count) return null;
  return (
    <>
      {view.open.map((clip) => (
        <ClipChip key={clip.clipId} clip={clip} nowSec={now} warnSec={view.hqWarnSec} />
      ))}
    </>
  );
}
