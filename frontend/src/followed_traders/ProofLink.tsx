/**
 * A trade's Proof link (operator ask 2026-10-13: "I want the proof to be a hover"). Hovering or focusing it shows the
 * trade's entry and exit screenshots in a card under it, so checking a trade never leaves the board; the pointer can
 * move into the card, and Escape closes it. Clicking the link or the card opens the whole Proof: what the vision read
 * at each, and every read in between. The images are asked for only once the card shows (FeedImage keeps them).
 */
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  FOLLOWED_PROOF_CARD_GAP_PX,
  FOLLOWED_PROOF_CARD_WIDTH_PX,
  FOLLOWED_PROOF_HOVER_CLOSE_MS,
  FOLLOWED_PROOF_HOVER_OPEN_MS,
  FT_ENTRY,
  FT_EXIT,
  FT_NO_EVIDENCE,
  FT_PROOF,
  FT_PROOF_CLICK_HINT,
} from './constants';
import { FeedImage } from './FeedImage';
import { entered, exited } from './format';
import { SideChip, Ticker, TickerMark } from './parts';
import { exitTs, noExitImage } from './proof';
import type { FollowedTrade } from './types';

interface Anchor { left: number; top: number; right: number; bottom: number }

/**
 * Under the link, its right edge on the link's (the link ends its row), so the row it proves stays readable; above
 * the link when there is no room under it; always inside the viewport. Pure.
 */
export function proofCardPosition(anchor: Anchor, size: { width: number; height: number },
  viewport: { width: number; height: number }, gap = FOLLOWED_PROOF_CARD_GAP_PX): { left: number; top: number } {
  const left = Math.max(gap, Math.min(anchor.right - size.width, viewport.width - gap - size.width));
  const under = anchor.bottom + gap;
  const top = under + size.height <= viewport.height - gap ? under
    : Math.max(gap, Math.min(anchor.top - gap - size.height, viewport.height - gap - size.height));
  return { left, top };
}

/** What the card shows: the entry and exit screenshots, each under its time. */
export function ProofPeek({ t }: { t: FollowedTrade }) {
  const out = exitTs(t);
  return (
    <>
      <div className="ft-peek__head">
        <span className="ft-strong">{t.trader}</span><SideChip side={t.side} /><Ticker symbol={t.symbol} className="ft-strong" />
        <TickerMark ticker={t.ticker} />
      </div>
      <div className="ft-peek__shot">
        <div className="ft-peek__label"><span className="ft-eyebrow ft-eyebrow--long">{FT_ENTRY}</span>
          <span className="ft-mono ft-muted ft-xs">{entered(t.entry)}</span></div>
        <FeedImage path={t.evidence.entry} className="ft-peek__img" missing={FT_NO_EVIDENCE}
          alt={`${t.trader}'s position bar at the entry`} />
      </div>
      <div className="ft-peek__shot">
        <div className="ft-peek__label"><span className="ft-eyebrow ft-eyebrow--exit">{FT_EXIT}</span>
          <span className="ft-mono ft-muted ft-xs">{t.exit && out !== null ? exited(t.exit) : ''}</span></div>
        {out === null || t.left_bar ? <div className="ft-empty ft-small">{noExitImage(t)}</div>
          : <FeedImage path={t.evidence.exit} className="ft-peek__img" missing={FT_NO_EVIDENCE}
            alt={`${t.trader}'s position bar at the exit`} />}
      </div>
      <span className="ft-muted ft-xs">{FT_PROOF_CLICK_HINT}</span>
    </>
  );
}

function Card({ t, anchor, onEnter, onLeave, onOpen }: {
  t: FollowedTrade; anchor: Anchor; onEnter: () => void; onLeave: () => void; onOpen: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const place = () => setPos(proofCardPosition(anchor, { width: el.offsetWidth, height: el.offsetHeight },
      { width: window.innerWidth, height: window.innerHeight }));
    place();
    // The screenshots arrive after the card shows and make it taller.
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(place) : null;
    ro?.observe(el);
    return () => ro?.disconnect();
  }, [anchor]);
  return createPortal(
    <div ref={ref} className="ft-peek" role="tooltip" data-testid={`ft-proof-card-${t.id}`}
      style={{ width: FOLLOWED_PROOF_CARD_WIDTH_PX, left: pos?.left ?? -9999, top: pos?.top ?? -9999 }}
      onMouseEnter={onEnter} onMouseLeave={onLeave} onClick={onOpen}>
      <ProofPeek t={t} />
    </div>,
    document.body,
  );
}

export function ProofLink({ t, onProof }: { t: FollowedTrade; onProof: (id: string) => void }) {
  const [anchor, setAnchor] = useState<Anchor | null>(null);
  // One timer: the wait before the card shows, or the grace before it goes.
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  // Escape closes the card wherever focus is: a card opened by the pointer leaves focus where it was.
  const shown = anchor !== null;
  useEffect(() => {
    if (!shown) return undefined;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      window.clearTimeout(timer.current);
      setAnchor(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [shown]);
  const show = (el: HTMLElement) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      const b = el.getBoundingClientRect();
      setAnchor({ left: b.left, top: b.top, right: b.right, bottom: b.bottom });
    }, FOLLOWED_PROOF_HOVER_OPEN_MS);
  };
  const keep = () => window.clearTimeout(timer.current);
  const leave = () => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setAnchor(null), FOLLOWED_PROOF_HOVER_CLOSE_MS);
  };
  const open = () => {
    window.clearTimeout(timer.current);
    setAnchor(null);
    onProof(t.id);
  };
  return (
    <>
      <button type="button" className="ft-link" onClick={open} data-testid={`ft-proof-${t.id}`}
        aria-label={`${FT_PROOF}: ${t.trader} ${t.side} ${t.symbol}`}
        onMouseEnter={(e) => show(e.currentTarget)} onMouseLeave={leave}
        onFocus={(e) => show(e.currentTarget)} onBlur={leave}>
        {FT_PROOF}
      </button>
      {anchor && <Card t={t} anchor={anchor} onEnter={keep} onLeave={leave} onOpen={open} />}
    </>
  );
}
