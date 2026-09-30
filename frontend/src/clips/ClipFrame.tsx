/**
 * The red frame around what a clip sees (ADR 039, mockup v1 board 2): drawn
 * over a Trader tab only while the operator points at its CLIP chip, so the
 * trading screen is never framed otherwise. The rest of the window dims a
 * little, and the labels say what is in the picture and what is left out.
 */
import { useEffect, useState, useSyncExternalStore, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { getClipsVersion, getHoveredClip, getClipsView, subscribeClips } from './clipsStore';
import { paneFor } from './clipTabReport';

export function ClipFrame({ rootRef }: { rootRef: RefObject<HTMLElement | null> }) {
  useSyncExternalStore(subscribeClips, getClipsVersion, () => 0);
  const hovered = getHoveredClip();
  const symbol = hovered ? getClipsView()?.open.find((o) => o.clipId === hovered)?.symbol ?? null : null;
  const [rect, setRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    if (!symbol) {
      setRect(null);
      return undefined;
    }
    let raf = 0;
    const measure = () => {
      const pane = paneFor(rootRef.current, symbol);
      const r = pane?.getBoundingClientRect() ?? null;
      setRect(r && r.width > 0 && r.height > 0 ? r : null);
      raf = window.requestAnimationFrame(measure);
    };
    measure();
    return () => window.cancelAnimationFrame(raf);
  }, [symbol, rootRef]);

  if (!symbol || !rect) return null;
  return createPortal(
    <div className="clip-frame" data-testid="clip-frame" aria-hidden="true" style={{ left: rect.left, top: rect.top, width: rect.width, height: rect.height }}>
      <span className="clip-frame__label">▶ In the clip: {symbol}&apos;s Trader tab</span>
      <span className="clip-frame__out">header left out</span>
    </div>,
    document.body,
  );
}
