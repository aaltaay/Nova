/**
 * Right-click a working order (operator ask 2026-10-14: "I should be able to do a right-click and cancel an
 * order"): a menu at the pointer that names the order and cancels it. It is the row's Cancel button, which
 * sits in the Actions column at the table's right end and is often scrolled out of view. It sends at once,
 * with no confirm: a cancel only takes risk away, and the padlock never holds one (ADR 018). The panel
 * closes the menu when its order leaves the working list, so it never offers to cancel an order that has
 * already filled. Focus stays where it was, so a hot key still reaches the desk.
 */
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import {
  WORKING_ORDER_MENU_CANCEL_LABEL,
  WORKING_ORDER_MENU_CAPTION,
  WORKING_ORDER_MENU_HINT_TAIL,
} from '../constants';
import { fmtPrice } from '../utils/quoteFormat';
import { displayFilledQty } from './orderFillHonesty';
import { formatOrderSide } from './orderDisplay';
import { remainingShares } from './orderQtyMath';
import type { IbkrOrder } from './types';
import './workingOrderMenu.css';

/** Which row the menu is for (its `orderRowKeys` key) and where the pointer was. */
export type WorkingOrderMenuAt = { key: string; x: number; y: number };

const GAP_PX = 4;
/** Mirrors `.working-order-menu { width }` in workingOrderMenu.css. */
export const WORKING_ORDER_MENU_WIDTH_PX = 272;

const shares = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 4 });

/** "Buy 1,000 at $4.00", "Sell 500, stop $3.80" -- the order as the operator placed it. */
export function workingOrderSummary(o: IbkrOrder): string {
  const head = `${formatOrderSide(o.side)} ${shares(o.qty)}`;
  const type = (o.order_type || '').toUpperCase().replace(/[\s_-]+/g, '');
  const limit = o.limit_price != null ? fmtPrice(o.limit_price) : null;
  const stop = o.stop_price != null ? fmtPrice(o.stop_price) : null;
  if ((type === 'STP' || type === 'STOP') && stop) return `${head}, stop ${stop}`;
  if ((type === 'STPLMT' || type === 'STOPLIMIT') && stop && limit) return `${head}, stop ${stop}, limit ${limit}`;
  if (type === 'MKT' || type === 'MARKET') return `${head} at market`;
  return limit ? `${head} at ${limit}` : head;
}

/** What Cancel takes away: the shares still working, and what stays. */
export function workingOrderCancelHint(o: IbkrOrder): string {
  const left = remainingShares(o);
  const filled = displayFilledQty(o);
  const lead = filled > 0
    ? `Cancels the ${shares(left)} shares still working; the ${shares(filled)} filled stay.`
    : `Cancels all ${shares(left)} shares.`;
  return `${lead} ${WORKING_ORDER_MENU_HINT_TAIL}`;
}

/** At the pointer, wholly on screen: a right-click low in the orders dock opens the menu upward. */
export function workingOrderMenuPosition(args: {
  x: number; y: number; viewportWidth: number; viewportHeight: number; menuHeight: number;
}): { top: number; left: number } {
  const left = Math.max(GAP_PX, Math.min(args.x, args.viewportWidth - WORKING_ORDER_MENU_WIDTH_PX - GAP_PX));
  const below = args.y + args.menuHeight + GAP_PX <= args.viewportHeight;
  const top = below ? args.y : Math.max(GAP_PX, args.y - args.menuHeight);
  return { top, left };
}

interface Props {
  order: IbkrOrder;
  x: number;
  y: number;
  /** Why Cancel is locked (last-known rows); the row's own Cancel says the same. */
  why?: string;
  onCancel: (orderId: number) => void;
  onClose: () => void;
}

export function WorkingOrderMenu({ order, x, y, why, onCancel, onClose }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [height, setHeight] = useState(0);

  useLayoutEffect(() => {
    const measured = ref.current?.getBoundingClientRect().height ?? 0;
    if (measured > 0 && Math.abs(measured - height) > 1) setHeight(measured);
  }, [height, order]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    const onDown = (event: MouseEvent) => {
      if (ref.current?.contains(event.target as Node)) return;
      onClose();
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mousedown', onDown);
    window.addEventListener('resize', onClose);
    window.addEventListener('blur', onClose);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mousedown', onDown);
      window.removeEventListener('resize', onClose);
      window.removeEventListener('blur', onClose);
    };
  }, [onClose]);

  const position = workingOrderMenuPosition({
    x, y, viewportWidth: window.innerWidth, viewportHeight: window.innerHeight, menuHeight: height,
  });
  return createPortal(
    <div
      ref={ref}
      className="working-order-menu"
      role="menu"
      aria-label={`${order.symbol} ${WORKING_ORDER_MENU_CAPTION}`}
      data-testid="working-order-menu"
      data-order-id={order.order_id}
      style={{ top: position.top, left: position.left, visibility: height > 0 ? undefined : 'hidden' }}
      onContextMenu={(event) => event.preventDefault()}
    >
      <div className="working-order-menu__head">
        <span className="working-order-menu__sym">{order.symbol}</span>
        <span className="working-order-menu__caption">{WORKING_ORDER_MENU_CAPTION}</span>
      </div>
      <div className="working-order-menu__order" data-testid="working-order-menu-order">
        {workingOrderSummary(order)}
      </div>
      <button
        type="button"
        role="menuitem"
        className="working-order-menu__row"
        data-testid="working-order-menu-cancel"
        disabled={Boolean(why)}
        data-why={why}
        onClick={() => {
          onClose();
          onCancel(order.order_id);
        }}
      >
        <span className="working-order-menu__icon" aria-hidden="true"><X size={15} /></span>
        <span className="working-order-menu__text">
          <span className="working-order-menu__label">{WORKING_ORDER_MENU_CANCEL_LABEL}</span>
          <span className="working-order-menu__hint">{workingOrderCancelHint(order)}</span>
        </span>
      </button>
    </div>,
    document.body,
  );
}
