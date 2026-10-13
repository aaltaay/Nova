/**
 * The Catalyst column's cell (was News; operator ask 2026-10-12): what is moving the stock -- its news, or with
 * no news the cause the rules read from the facts (ADR 028) -- as a mark, a word and a short second line.
 * Hovering (or focusing) it opens everything behind the call (`CatalystExplain`) in a card beside it; the pointer
 * can move into the card. `compact` shows the mark alone (the narrow focus rail). On a board, `board` reads the
 * row that board shows, at its price. Until the read is in -- and on an API from before the batch read, or the
 * sample desk -- the cell shows what its table showed as the News column (`fallback`), never a guess.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import {
  CATALYST_HOVER_CLOSE_MS,
  CATALYST_HOVER_GAP_PX,
  CATALYST_HOVER_OPEN_MS,
  CATALYST_HOVER_WIDTH_PX,
} from '../constants';
import { useCatalystRead } from '../hooks/useCatalystRead';
import type { CatalystVerdict } from '../types/catalystVerdict';
import { catalystFace } from '../utils/catalystCause';
import { CatalystExplain } from './CatalystExplain';
import { CatalystMark } from './CatalystMark';
import './catalystCell.css';

interface Anchor { left: number; top: number; right: number; bottom: number }

/** Beside the cell (right, else left), top-aligned, inside the viewport. Pure. */
export function catalystCardPosition(anchor: Anchor, size: { width: number; height: number },
  viewport: { width: number; height: number }, gap = CATALYST_HOVER_GAP_PX): { left: number; top: number } {
  const right = anchor.right + gap;
  const left = right + size.width <= viewport.width - gap ? right : Math.max(gap, anchor.left - gap - size.width);
  const top = Math.max(gap, Math.min(anchor.top, viewport.height - gap - size.height));
  return { left, top };
}

function HoverCard({ anchor, children, onEnter, onLeave }: {
  anchor: Anchor; children: ReactNode; onEnter: () => void; onLeave: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const place = () => setPos(catalystCardPosition(anchor, { width: el.offsetWidth, height: el.offsetHeight },
      { width: window.innerWidth, height: window.innerHeight }));
    place();
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(place) : null;
    ro?.observe(el);
    return () => ro?.disconnect();
  }, [anchor]);
  return createPortal(
    <div ref={ref} className="cc-card" role="tooltip" data-testid="catalyst-card"
      style={{ width: CATALYST_HOVER_WIDTH_PX, left: pos?.left ?? -9999, top: pos?.top ?? -9999 }}
      onMouseEnter={onEnter} onMouseLeave={onLeave}
      // The card is the row's child in React's tree: a click in it never selects the row or opens the Trader.
      onClick={e => e.stopPropagation()} onDoubleClick={e => e.stopPropagation()}
      onMouseDown={e => e.stopPropagation()} onContextMenu={e => e.stopPropagation()}>
      {children}
    </div>,
    document.body,
  );
}

interface Props {
  symbol: string;
  /** The board this row is on (gappers | gainers | losers | afterhours | large_cap); null off a board. */
  board: string | null;
  /** The row's own news verdict (the hover names its headline while the read has none). */
  verdict?: CatalystVerdict | null;
  /** What the table showed as the News column: shown until the read is in, and instead of it when none can be. */
  fallback: ReactNode;
  /** The mark alone, the word on hover (a narrow column). */
  compact?: boolean;
  /** False when the caller shows its own card (the focus rail). */
  hover?: boolean;
}

export function CatalystCell({ symbol, board, verdict = null, fallback, compact = false, hover = true }: Props) {
  const r = useCatalystRead(symbol, board);
  const [anchor, setAnchor] = useState<Anchor | null>(null);
  const openTimer = useRef<number | null>(null);
  const closeTimer = useRef<number | null>(null);
  const clear = () => {
    if (openTimer.current != null) window.clearTimeout(openTimer.current);
    if (closeTimer.current != null) window.clearTimeout(closeTimer.current);
    openTimer.current = closeTimer.current = null;
  };
  useEffect(() => clear, []);
  const open = useCallback((el: HTMLElement) => {
    clear();
    openTimer.current = window.setTimeout(() => {
      const b = el.getBoundingClientRect();
      setAnchor({ left: b.left, top: b.top, right: b.right, bottom: b.bottom });
    }, CATALYST_HOVER_OPEN_MS);
  }, []);
  const keep = useCallback(() => clear(), []);
  const close = useCallback(() => {
    clear();
    closeTimer.current = window.setTimeout(() => setAnchor(null), CATALYST_HOVER_CLOSE_MS);
  }, []);

  if (r.unavailable) return <>{fallback}</>;
  const nowMs = r.read?.replay ? r.read.generated_at * 1000 : Date.now();
  const face = catalystFace(r.read, verdict, nowMs, r.loading);
  const label = [face.word, face.detail].filter(Boolean).join(' -- ') || r.read?.likely.label || r.error || '';
  return (
    <span
      className={`cc-cell${compact ? ' cc-cell--compact' : ''}`}
      data-testid={`catalyst-cell-${symbol}`}
      data-catalyst-kind={face.kind}
      tabIndex={hover ? 0 : undefined}
      aria-label={label}
      onMouseEnter={hover ? e => open(e.currentTarget) : undefined}
      onMouseLeave={hover ? close : undefined}
      onFocus={hover ? e => open(e.currentTarget) : undefined}
      onBlur={hover ? close : undefined}
    >
      {r.read ? <CatalystMark face={face} /> : fallback}
      {r.read && !compact && face.word && (
        <span className="cc-text">
          <span className="cc-word">{face.word}</span>
          {face.detail && <span className="cc-detail">{face.detail}</span>}
        </span>
      )}
      {hover && anchor && (
        <HoverCard anchor={anchor} onEnter={keep} onLeave={close}>
          <CatalystExplain symbol={symbol} read={r.read} loading={r.loading} error={r.error} rowVerdict={verdict} />
        </HoverCard>
      )}
    </span>
  );
}
