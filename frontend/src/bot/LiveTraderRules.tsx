/**
 * A host bot's rules in a card under its Rules button (LiveTraderStrip): the rules as chips, then their editor
 * (LiveTraderSettings), Paper only. Drawn over the page (a portal), since the host's card clips what overflows it;
 * it opens below the button, or above when there is no room, follows the button when the page scrolls, and closes
 * on Done, Escape, a click elsewhere, or the button scrolling out of the window.
 */
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { LT_DONE, LT_PAPER_ONLY, ltBotOf } from '../constantGroups/live_trader';
import { ruleChips } from './liveTraderFormat';
import { LiveTraderSettings } from './LiveTraderSettings';
import type { LtHost, LtPatch } from './liveTraderTypes';

const GAP_PX = 6;
const EDGE_PX = 12;

interface Props {
  anchor: HTMLElement;
  host: LtHost;
  sellAllAt: string;
  busy: boolean;
  onPatch: (name: string, body: LtPatch) => Promise<void>;
  onClose: () => void;
}

export function LiveTraderRules({ anchor, host, sellAllAt, busy, onPatch, onClose }: Props) {
  const card = useRef<HTMLDivElement>(null);
  const [at, setAt] = useState<{ left: number; top: number } | null>(null);

  useLayoutEffect(() => {
    const place = () => {
      const a = anchor.getBoundingClientRect();
      // Scrolled out of the window (the stack scrolls when the hosts do not fit): the card has nothing to sit under.
      if (a.bottom < 0 || a.top > window.innerHeight) {
        onClose();
        return;
      }
      const box = card.current?.getBoundingClientRect();
      const w = box?.width ?? 0;
      const h = box?.height ?? 0;
      const below = a.bottom + GAP_PX;
      const top = below + h > window.innerHeight - EDGE_PX ? Math.max(EDGE_PX, a.top - GAP_PX - h) : below;
      const left = Math.max(EDGE_PX, Math.min(a.left, window.innerWidth - EDGE_PX - w));
      setAt((prev) => (prev && prev.left === left && prev.top === top ? prev : { left, top }));
    };
    place();
    // The page's stack and the page itself scroll rather than the window (Codex review, PR #1009): a scroll anywhere
    // moves the button, so the card follows it. Scroll events do not bubble; the capture phase sees every one.
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [anchor, host, onClose]);

  useEffect(() => {
    const away = (e: MouseEvent) => {
      const target = e.target as Node;
      if (!card.current?.contains(target) && !anchor.contains(target)) onClose();
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('mousedown', away);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', away);
      document.removeEventListener('keydown', esc);
    };
  }, [anchor, onClose]);

  return createPortal(
    <div ref={card} className="lt-pop" role="dialog" aria-label={`${ltBotOf(host.name)}: rules`}
      data-testid={`lt-rules-card-${host.name}`}
      style={at ? { left: at.left, top: at.top } : { left: -9999, top: -9999 }}>
      <div className="lt-pop__head">
        <b>{ltBotOf(host.name)}</b>
        <span className="lt-muted">{LT_PAPER_ONLY}</span>
        <button type="button" className="lt-linkbtn" data-testid={`lt-rules-done-${host.name}`} onClick={onClose}>{LT_DONE}</button>
      </div>
      <div className="lt-pop__chips">
        {ruleChips(host.settings, sellAllAt).map(chip => <span key={chip} className="lt-chip">{chip}</span>)}
      </div>
      <LiveTraderSettings name={host.name} settings={host.settings} busy={busy} onPatch={onPatch} />
    </div>,
    document.body,
  );
}
