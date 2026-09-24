/**
 * The ticket's hover card: what a side or an order type does, with a small
 * example chart (OrderExplainerArt.tsx) and the words from
 * orderExplainerCopy.ts. Shown by useOrderExplainer.tsx; pointer-events none,
 * so it never takes a click from the ticket.
 *
 * It sits beside the ticket (left, else right) so it never covers the control
 * under the pointer or the "why is this locked" tip below it (ux/whyTip.ts);
 * a window too narrow for either side puts it above the control.
 */
import { useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  ArrowDownRight,
  ArrowUpRight,
  Footprints,
  ShieldAlert,
  ShieldCheck,
  Target,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { OrderExplainerArt } from './OrderExplainerArt';
import { ORDER_EXPLAINERS, type OrderExplainerKind } from './orderExplainerCopy';
import './orderExplainer.css';

const EXPLAINER_GAP_PX = 10;
const EXPLAINER_EDGE_PX = 8;

const ICONS: Readonly<Record<OrderExplainerKind, LucideIcon>> = {
  buy: ArrowUpRight,
  sell: ArrowDownRight,
  LMT: Target,
  MKT: Zap,
  STP: ShieldAlert,
  'STP LMT': ShieldCheck,
  TRAIL: Footprints,
};

interface Props {
  id: string;
  kind: OrderExplainerKind;
  anchor: HTMLElement;
  onDismiss: () => void;
}

interface Spot {
  top: number;
  left: number;
  side: 'left' | 'right' | 'above' | 'below';
}

/** Where the card goes: beside the ticket, else above (or below) the control. */
export function placeExplainer(
  anchor: DOMRect,
  ticket: DOMRect,
  card: { width: number; height: number },
  view: { width: number; height: number },
): Spot {
  const clampTop = (top: number) =>
    Math.min(Math.max(top, EXPLAINER_EDGE_PX), Math.max(EXPLAINER_EDGE_PX, view.height - EXPLAINER_EDGE_PX - card.height));
  const beside = clampTop(anchor.top + anchor.height / 2 - card.height / 2);
  if (ticket.left - EXPLAINER_GAP_PX - card.width >= EXPLAINER_EDGE_PX) {
    return { top: beside, left: ticket.left - EXPLAINER_GAP_PX - card.width, side: 'left' };
  }
  if (ticket.right + EXPLAINER_GAP_PX + card.width <= view.width - EXPLAINER_EDGE_PX) {
    return { top: beside, left: ticket.right + EXPLAINER_GAP_PX, side: 'right' };
  }
  const left = Math.min(
    Math.max(anchor.left + anchor.width / 2 - card.width / 2, EXPLAINER_EDGE_PX),
    Math.max(EXPLAINER_EDGE_PX, view.width - EXPLAINER_EDGE_PX - card.width),
  );
  const above = anchor.top - EXPLAINER_GAP_PX - card.height;
  if (above >= EXPLAINER_EDGE_PX) return { top: above, left, side: 'above' };
  return { top: clampTop(anchor.bottom + EXPLAINER_GAP_PX), left, side: 'below' };
}

export function OrderExplainerCard({ id, kind, anchor, onDismiss }: Props) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [spot, setSpot] = useState<Spot | null>(null);
  const doc = anchor.ownerDocument;
  const copy = ORDER_EXPLAINERS[kind];
  const Icon = ICONS[kind];

  useLayoutEffect(() => {
    const card = cardRef.current;
    const view = doc.defaultView;
    if (!card || !view) return;
    if (!anchor.isConnected) {
      onDismiss();
      return;
    }
    const ticket = anchor.closest('.manual-order-ticket') ?? anchor;
    setSpot(
      placeExplainer(
        anchor.getBoundingClientRect(),
        ticket.getBoundingClientRect(),
        { width: card.offsetWidth, height: card.offsetHeight },
        {
          width: doc.documentElement.clientWidth || view.innerWidth,
          height: doc.documentElement.clientHeight || view.innerHeight,
        },
      ),
    );
    // The card is placed once; anything that moves the ticket closes it.
    view.addEventListener('scroll', onDismiss, true);
    view.addEventListener('resize', onDismiss);
    return () => {
      view.removeEventListener('scroll', onDismiss, true);
      view.removeEventListener('resize', onDismiss);
    };
  }, [anchor, doc, kind, onDismiss]);

  return createPortal(
    <div
      ref={cardRef}
      id={id}
      role="tooltip"
      className={`order-explainer order-explainer--${copy.tone}${spot ? ` is-${spot.side}` : ''}`}
      style={spot ? { top: spot.top, left: spot.left } : { visibility: 'hidden' }}
      data-testid="order-explainer"
      data-kind={kind}
    >
      <div className="order-explainer__head">
        <span className="order-explainer__icon" aria-hidden="true">
          <Icon size={15} strokeWidth={2.4} />
        </span>
        <span className="order-explainer__title">{copy.title}</span>
        <span className="order-explainer__group">{copy.group}</span>
      </div>
      <p className="order-explainer__summary">
        {copy.summary.map((part, index) =>
          typeof part === 'string' ? (
            part
          ) : (
            <strong key={index} className={part.tone ? `order-explainer__em--${part.tone}` : undefined}>
              {part.strong}
            </strong>
          ),
        )}
      </p>
      <figure className="order-explainer__figure">
        <figcaption className="order-explainer__caption">{copy.caption}</figcaption>
        <OrderExplainerArt kind={kind} />
        <ul className="order-explainer__legend">
          {copy.legend.map(item => (
            <li key={item.text}>
              <span className={`order-explainer__mark order-explainer__mark--${item.mark}`} aria-hidden="true" />
              {item.text}
            </li>
          ))}
        </ul>
      </figure>
      <ul className="order-explainer__facts">
        {copy.facts.map(fact => (
          <li key={fact}>{fact}</li>
        ))}
      </ul>
    </div>,
    doc.body,
  );
}
