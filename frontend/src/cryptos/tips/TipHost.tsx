/**
 * The Cryptos page's hover card (ADR 040, operator ask: "when the user hover over things, make sure you show in
 * friendly visual way what does it mean"). One card per page: hovering (or focusing) anything that explains
 * itself shows what it means in plain words, a small drawing with today's reading on it, what it reads now and
 * why a trader cares. The card takes no pointer events, so it never covers what it explains.
 */
import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { TipVisual, type TipVisualSpec } from './TipVisuals';
import './cryptoTip.css';

export type TipTone = 'up' | 'down' | 'warn' | 'accent' | 'muted' | 'violet';

export interface TipContent {
  title: string;
  tone?: TipTone;
  /** What it is, in one or two plain sentences. */
  what: string;
  visual?: TipVisualSpec;
  /** The reading right now. */
  now?: string | null;
  /** Why a trader cares. */
  why?: string | null;
  /** Where the number comes from. */
  source?: string | null;
}

interface Shown {
  content: TipContent;
  rect: { left: number; top: number; right: number; bottom: number; width: number };
}

type Show = (make: (() => TipContent | null) | null, el?: Element | null) => void;

const TipContext = createContext<Show>(() => undefined);

/** Delay before the first card shows; moving between explained things answers at once. */
export const CRYPTO_TIP_DELAY_MS = 140;
const GAP = 10;
const EDGE = 8;

export function TipHost({ children }: { children: ReactNode }) {
  const [shown, setShown] = useState<Shown | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const up = useRef(false);

  const show = useCallback<Show>((make, el) => {
    window.clearTimeout(timer.current);
    if (!make || !el) {
      timer.current = window.setTimeout(() => {
        up.current = false;
        setShown(null);
      }, 60);
      return;
    }
    const open = () => {
      const content = make();
      if (!content) return;
      const r = el.getBoundingClientRect();
      up.current = true;
      setShown({ content, rect: { left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width } });
    };
    if (up.current) open();
    else timer.current = window.setTimeout(open, CRYPTO_TIP_DELAY_MS);
  }, []);

  useEffect(() => {
    const hide = () => {
      window.clearTimeout(timer.current);
      up.current = false;
      setShown(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') hide();
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('scroll', hide, true);
    window.addEventListener('resize', hide);
    return () => {
      window.clearTimeout(timer.current);
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('scroll', hide, true);
      window.removeEventListener('resize', hide);
    };
  }, []);

  return (
    <TipContext.Provider value={show}>
      {children}
      {shown && typeof document !== 'undefined' ? createPortal(<TipCard shown={shown} />, document.body) : null}
    </TipContext.Provider>
  );
}

function TipCard({ shown }: { shown: Shown }) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const { content, rect } = shown;

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    const vw = document.documentElement.clientWidth || window.innerWidth;
    const vh = document.documentElement.clientHeight || window.innerHeight;
    let top = rect.bottom + GAP;
    if (top + h > vh - EDGE && rect.top - GAP - h >= EDGE) top = rect.top - GAP - h;
    top = Math.max(EDGE, Math.min(top, vh - EDGE - h));
    const left = Math.min(Math.max(rect.left + rect.width / 2 - w / 2, EDGE), Math.max(EDGE, vw - EDGE - w));
    setPos({ left: Math.round(left), top: Math.round(top) });
  }, [rect.bottom, rect.left, rect.top, rect.width, content]);

  return (
    <div
      ref={ref}
      className={`cx-tip cx-tip--${content.tone ?? 'accent'}`}
      role="tooltip"
      data-testid="crypto-tip"
      style={pos ? { left: pos.left, top: pos.top } : { left: -9999, top: -9999 }}
    >
      <div className="cx-tip__title">
        <span className="cx-tip__dot" aria-hidden />
        {content.title}
      </div>
      <p className="cx-tip__what">{content.what}</p>
      {content.visual ? <TipVisual spec={content.visual} /> : null}
      {content.now ? (
        <p className="cx-tip__now">
          <span className="cx-tip__label">Now</span>
          {content.now}
        </p>
      ) : null}
      {content.why ? (
        <p className="cx-tip__why">
          <span className="cx-tip__label">Why it matters</span>
          {content.why}
        </p>
      ) : null}
      {content.source ? <p className="cx-tip__source">{content.source}</p> : null}
    </div>
  );
}

/** Props that make an element explain itself: `<td {...tip(() => content)}>`. */
export function useTip(): (make: () => TipContent | null) => {
  onMouseEnter: (e: { currentTarget: Element }) => void;
  onMouseLeave: () => void;
  onFocus: (e: { currentTarget: Element }) => void;
  onBlur: () => void;
  'data-cx-tip': '';
} {
  const show = useContext(TipContext);
  return (make) => ({
    onMouseEnter: (e) => show(make, e.currentTarget),
    onMouseLeave: () => show(null),
    onFocus: (e) => show(make, e.currentTarget),
    onBlur: () => show(null),
    'data-cx-tip': '',
  });
}
