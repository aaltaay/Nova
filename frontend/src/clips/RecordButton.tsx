/**
 * The red ● on every Trader tab strip (ADR 039): opens the Record menu for
 * the active tab's symbol, and counts up while that symbol's clip records, so
 * the clip can be stopped from where the operator is.
 */
import { useEffect, useRef, useState } from 'react';
import { clockLabel, openClipFor } from './clipModel';
import { CLIP_BUTTON_LABEL, CLIP_BUTTON_TITLE } from './clipsConstants';
import { useClips } from './clipsStore';
import { RecordMenu } from './RecordMenu';

export function RecordButton({ symbol }: { symbol: string | null }) {
  const { view } = useClips();
  const [open, setOpen] = useState(false);
  const [now, setNow] = useState(() => Date.now() / 1000);
  const ref = useRef<HTMLButtonElement>(null);
  const clip = openClipFor(view, symbol);

  useEffect(() => {
    if (!clip) return undefined;
    const id = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(id);
  }, [clip]);
  useEffect(() => {
    if (!symbol) setOpen(false);
  }, [symbol]);

  const cls = `clip-rec-btn${open ? ' is-open' : ''}${clip ? ' is-on' : ''}`;
  return (
    <>
      <button
        ref={ref}
        type="button"
        className={cls}
        data-testid="clip-record-button"
        aria-haspopup="dialog"
        aria-expanded={open}
        title={symbol ? `${CLIP_BUTTON_TITLE} (${symbol})` : ''}
        disabled={!symbol}
        data-why={!symbol ? 'Type a ticker in the new tab first' : undefined}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="clip-rec-btn__dot" aria-hidden="true" />
        <span className="clip-rec-btn__label">{clip ? clockLabel(now - clip.startedTs) : CLIP_BUTTON_LABEL}</span>
        <span className="clip-rec-btn__caret" aria-hidden="true">▾</span>
      </button>
      {open && symbol && ref.current ? <RecordMenu symbol={symbol} anchor={ref.current} onClose={() => setOpen(false)} /> : null}
    </>
  );
}
