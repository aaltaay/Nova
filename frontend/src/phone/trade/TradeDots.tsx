/**
 * The two small dots over the Trade screen (frozen mockup R2-Trade): your position in this stock, and
 * your working orders. Tap a dot to see what it holds; press and hold it to flatten, or to cancel every
 * order, behind a warning that fills the screen. Drag a dot anywhere: it stays where you leave it.
 *
 * A dot is drawn only while it has something to show.
 */
import { useCallback, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react';
import { Briefcase, Clock, TriangleAlert } from 'lucide-react';
import type { IbkrOrder } from '../../ibkr/types';
import { plainPrice } from '../../utils/priceTick';
import { readPref, writePref } from '../../utils/prefStore';
import { signedMoney, toneClass } from '../phoneFormat';
import type { PhoneTrade } from './usePhoneTrade';

export type Ask = 'flatten' | 'cancel';

interface Spot { x: number; y: number }
type Spots = Record<'pos' | 'ord', Spot>;

/** Where each dot's centre sits, as a share of the screen: the mockup's places, at the right edge by the book. */
const DEFAULT_SPOTS: Spots = { pos: { x: 0.936, y: 0.56 }, ord: { x: 0.936, y: 0.61 } };
const SPOTS_KEY = 'nova.phone.trade.dots';
const HOLD_MS = 600;
const DRAG_PX = 8;
const EDGE = 0.06;

function clamp(n: number): number {
  return Math.min(1 - EDGE, Math.max(EDGE, n));
}

function asSpot(raw: unknown): Spot | null {
  const s = raw as Partial<Spot> | null;
  return s && typeof s.x === 'number' && typeof s.y === 'number' && Number.isFinite(s.x) && Number.isFinite(s.y)
    ? { x: clamp(s.x), y: clamp(s.y) } : null;
}

function readSpots(): Spots {
  return readPref<Spots>(SPOTS_KEY, DEFAULT_SPOTS, (raw) => {
    const r = raw as Partial<Record<'pos' | 'ord', unknown>> | null;
    const pos = asSpot(r?.pos);
    const ord = asSpot(r?.ord);
    return pos && ord ? { pos, ord } : null;
  });
}

export function orderLine(o: IbkrOrder): string {
  const shares = (o.remaining_qty ?? o.qty).toLocaleString('en-US');
  const side = o.side === 'BUY' ? 'Buy' : 'Sell';
  if (o.order_type === 'STP' && o.stop_price != null) return `${side} ${shares} ${o.symbol} stop ${plainPrice(o.stop_price)}`;
  if (o.limit_price != null) return `${side} ${shares} ${o.symbol} at ${plainPrice(o.limit_price)}`;
  return `${side} ${shares} ${o.symbol} at market`;
}

function Dot({ which, spot, count, label, children, onTap, onHold, onMove }: {
  which: 'pos' | 'ord';
  spot: Spot;
  count: number;
  label: string;
  children: ReactNode;
  onTap: () => void;
  onHold: () => void;
  onMove: (spot: Spot, done: boolean) => void;
}) {
  const press = useRef<{ x: number; y: number; dragged: boolean; held: boolean; timer: number | null } | null>(null);

  const end = (): void => {
    const p = press.current;
    if (p?.timer != null) window.clearTimeout(p.timer);
    press.current = null;
  };
  const spotAt = (ev: ReactPointerEvent<HTMLButtonElement>): Spot | null => {
    const screen = ev.currentTarget.closest('.ph-screen')?.getBoundingClientRect();
    if (!screen || !screen.width || !screen.height) return null;
    return { x: clamp((ev.clientX - screen.left) / screen.width), y: clamp((ev.clientY - screen.top) / screen.height) };
  };

  return (
    <button
      type="button"
      className="ph-dot"
      data-which={which}
      data-testid={`phone-dot-${which}`}
      aria-label={label}
      style={{ left: `${spot.x * 100}%`, top: `${spot.y * 100}%` }}
      onPointerDown={(ev) => {
        ev.currentTarget.setPointerCapture(ev.pointerId);
        const timer = window.setTimeout(() => {
          const p = press.current;
          if (!p || p.dragged) return;
          p.held = true;
          onHold();
        }, HOLD_MS);
        press.current = { x: ev.clientX, y: ev.clientY, dragged: false, held: false, timer };
      }}
      onPointerMove={(ev) => {
        const p = press.current;
        if (!p || p.held) return;
        if (!p.dragged && Math.hypot(ev.clientX - p.x, ev.clientY - p.y) < DRAG_PX) return;
        p.dragged = true;
        const next = spotAt(ev);
        if (next) onMove(next, false);
      }}
      onPointerUp={(ev) => {
        const p = press.current;
        const next = p?.dragged ? spotAt(ev) : null;
        end();
        if (!p || p.held) return;
        if (p.dragged) {
          if (next) onMove(next, true);
          return;
        }
        onTap();
      }}
      onPointerCancel={end}
      // The dot's own handlers decide tap, hold and drag; a long press must not open the browser's menu.
      onContextMenu={(ev) => ev.preventDefault()}
    >
      <span>{children}</span>
      <i aria-hidden="true">{count}</i>
    </button>
  );
}

export function TradeDots({ trade, onAsk }: { trade: PhoneTrade; onAsk: (ask: Ask) => void }) {
  const [spots, setSpots] = useState<Spots>(readSpots);
  const [open, setOpen] = useState<'pos' | 'ord' | null>(null);
  const { symbol, position, heldQty, working } = trade;

  const move = useCallback((which: 'pos' | 'ord') => (spot: Spot, done: boolean) => {
    setOpen(null);
    setSpots((prev) => {
      const next = { ...prev, [which]: spot };
      if (done) writePref(SPOTS_KEY, next);
      return next;
    });
  }, []);

  const showPos = heldQty !== 0 && position != null;
  const showOrd = working.length > 0;
  const which = open === 'pos' && showPos ? 'pos' : open === 'ord' && showOrd ? 'ord' : null;
  const anchor = which ? spots[which] : null;
  const first = working[0];

  return (
    <>
      {showPos ? (
        <Dot
          which="pos"
          spot={spots.pos}
          count={1}
          label={`Your ${symbol} position. Tap to see it, hold to flatten. Drag to move`}
          onTap={() => setOpen(open === 'pos' ? null : 'pos')}
          onHold={() => {
            setOpen(null);
            onAsk('flatten');
          }}
          onMove={move('pos')}
        >
          <Briefcase size={14} aria-hidden="true" />
        </Dot>
      ) : null}
      {showOrd ? (
        <Dot
          which="ord"
          spot={spots.ord}
          count={working.length}
          label={`Working orders: ${working.length}. Tap to see them, hold to cancel all. Drag to move`}
          onTap={() => setOpen(open === 'ord' ? null : 'ord')}
          onHold={() => {
            setOpen(null);
            onAsk('cancel');
          }}
          onMove={move('ord')}
        >
          <Clock size={14} aria-hidden="true" />
        </Dot>
      ) : null}
      {which && anchor ? (
        <div
          className="ph-dotpop"
          role="dialog"
          aria-label={which === 'pos' ? 'Your position' : 'Working orders'}
          data-testid="phone-dot-pop"
          style={{
            top: `${Math.min(0.78, Math.max(0.08, anchor.y - 0.05)) * 100}%`,
            ...(anchor.x > 0.5 ? { right: `calc(${(1 - anchor.x) * 100}% + 22px)` } : { left: `calc(${anchor.x * 100}% + 22px)` }),
          }}
        >
          {which === 'pos' && position ? (
            <>
              <div className="ph-label">Position</div>
              <div className="ph-dotpop__line">
                <span>{heldQty > 0 ? 'Long' : 'Short'} {Math.abs(heldQty).toLocaleString('en-US')} at {position.avg_cost != null ? plainPrice(position.avg_cost) : '—'}</span>
                <b className={toneClass(position.unrealized_pnl)}>{signedMoney(position.unrealized_pnl, 0)}</b>
              </div>
              <button type="button" onClick={() => { setOpen(null); onAsk('flatten'); }}>
                Flatten {Math.abs(heldQty).toLocaleString('en-US')} at {heldQty > 0 ? 'Bid' : 'Ask'}
              </button>
              <div className="ph-dotpop__note">Or press and hold the dot to flatten.</div>
            </>
          ) : (
            <>
              <div className="ph-label">Working · {working.length}</div>
              <div className="ph-dotpop__line"><span>{first ? orderLine(first) : ''}</span>{working.length > 1 ? <b>+{working.length - 1}</b> : null}</div>
              <button type="button" onClick={() => { setOpen(null); onAsk('cancel'); }}>Cancel all working orders</button>
              <div className="ph-dotpop__note">Or press and hold the dot to cancel all.</div>
            </>
          )}
        </div>
      ) : null}
    </>
  );
}

/** The warning that fills the screen before a flatten or a cancel of everything. */
export function TradeAsk({ ask, trade, onNo, onYes }: { ask: Ask; trade: PhoneTrade; onNo: () => void; onYes: () => void }) {
  const { symbol, heldQty, bid, ask: askPx, working, workingHere } = trade;
  const flat = ask === 'flatten';
  const shares = Math.abs(heldQty).toLocaleString('en-US');
  const at = heldQty > 0 ? bid : askPx;
  const orders = (n: number): string => `${n} working order${n === 1 ? '' : 's'}`;
  const first = working[0];
  const body = flat
    ? `${heldQty > 0 ? 'Sells' : 'Buys back'} all ${shares} shares at the ${heldQty > 0 ? 'Bid' : 'Ask'}${at != null ? `, ${plainPrice(at)},` : ''} right now${workingHere.length ? `, and cancels ${symbol}'s ${orders(workingHere.length)}` : ''}.`
    : working.length === 1 && first
      ? `1 order will be cancelled: ${orderLine(first)}.${heldQty ? ` Your ${shares} shares stay open.` : ''}`
      : `${orders(working.length)} will be cancelled, on every stock.${heldQty ? ` Your ${shares} shares stay open.` : ''}`;
  return (
    <div className="ph-ask" role="alertdialog" aria-modal="true" aria-label={flat ? `Flatten ${symbol}?` : 'Cancel working orders?'} data-testid="phone-ask">
      <div className="ph-ask__card">
        <span className="ph-ask__icon" aria-hidden="true"><TriangleAlert size={26} /></span>
        <b>{flat ? `Flatten ${symbol}?` : 'Cancel working orders?'}</b>
        <p>{body}</p>
        <div className="ph-ask__btns">
          <button type="button" onClick={onNo}>{flat ? 'Keep position' : 'Keep orders'}</button>
          <button type="button" className="is-do" onClick={onYes} data-testid="phone-ask-yes">
            {flat ? `Flatten ${shares}` : `Cancel ${working.length === 1 ? '1 order' : `${working.length} orders`}`}
          </button>
        </div>
      </div>
    </div>
  );
}
