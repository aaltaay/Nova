/**
 * The little price charts on the ticket's hover card (OrderExplainerCard.tsx):
 * one example per side and order type, drawn in the card's colours
 * (orderExplainer.css). Price runs up the chart, time to the right. Point marks
 * are explained by the card's legend; only lines and zones carry words here.
 */
import type { JSX } from 'react';
import type { OrderExplainerKind } from './orderExplainerCopy';

const W = 256;
const H = 100;
const LEFT = 8;
const RIGHT = W - 6;

type Tone = 'buy' | 'sell' | 'stop' | 'limit' | 'muted';

function Level({ y, tone, label, from = LEFT }: { y: number; tone: Tone; label?: string; from?: number }) {
  return (
    <g>
      <line className={`otx-level otx-stroke--${tone}`} x1={from} y1={y} x2={RIGHT} y2={y} />
      {label ? (
        <text className={`otx-label otx-fill--${tone}`} x={RIGHT} y={y - 4} textAnchor="end">
          {label}
        </text>
      ) : null}
    </g>
  );
}

function Price({ d, after = false }: { d: string; after?: boolean }) {
  return <path className={`otx-price${after ? ' otx-price--after' : ''}`} d={d} />;
}

function Fill({ x, y, tone }: { x: number; y: number; tone: 'buy' | 'sell' }) {
  return <circle className={`otx-dot otx-fill--${tone}`} cx={x} cy={y} r={4.5} />;
}

function Trigger({ x, y }: { x: number; y: number }) {
  return <circle className="otx-ring" cx={x} cy={y} r={6.5} />;
}

function Zone({ x, y, w, h, tone }: { x: number; y: number; w: number; h: number; tone: Tone }) {
  return <rect className={`otx-zone otx-fill--${tone}`} x={x} y={y} width={w} height={h} rx={3} />;
}

function Note({ x, y, tone, text, anchor = 'start' }: {
  x: number;
  y: number;
  tone: Tone;
  text: string;
  anchor?: 'start' | 'middle' | 'end';
}) {
  return (
    <text className={`otx-label otx-fill--${tone}`} x={x} y={y} textAnchor={anchor}>
      {text}
    </text>
  );
}

function BuyArt() {
  return (
    <>
      <Zone x={48} y={6} w={RIGHT - 48} h={50} tone="buy" />
      <Zone x={48} y={56} w={RIGHT - 48} h={38} tone="sell" />
      <Level y={56} tone="muted" label="your price" />
      <Note x={52} y={18} tone="buy" text="profit" />
      <Note x={52} y={88} tone="sell" text="loss" />
      <Price d="M8,64 L20,60 L34,62 L48,56 L64,62 L82,48 L100,53 L120,38 L140,43 L162,28 L184,33 L208,18 L230,22 L250,12" />
      <Fill x={48} y={56} tone="buy" />
    </>
  );
}

function SellArt() {
  return (
    <>
      <Zone x={26} y={34} w={108} h={32} tone="buy" />
      <Note x={32} y={46} tone="buy" text="your gain" />
      <Price d="M8,74 L26,66 L44,70 L62,56 L80,60 L98,46 L116,50 L134,34" />
      <Price after d="M134,34 L152,44 L170,30 L188,52 L206,40 L226,62 L250,54" />
      <Note x={RIGHT} y={90} tone="muted" text="after the sale: not yours" anchor="end" />
      <Fill x={26} y={66} tone="buy" />
      <Fill x={134} y={34} tone="sell" />
    </>
  );
}

function LimitArt() {
  return (
    <>
      <Zone x={LEFT} y={6} w={132} h={56} tone="limit" />
      <Note x={14} y={16} tone="limit" text="waiting" />
      <Level y={62} tone="limit" label="your limit" />
      <Price d="M8,26 L28,30 L48,24 L68,38 L88,34 L108,48 L128,56 L140,62 L158,52 L178,56 L198,42 L220,46 L250,34" />
      <Fill x={140} y={62} tone="buy" />
    </>
  );
}

function MarketArt() {
  return (
    <>
      <line className="otx-level otx-stroke--muted" x1={148} y1={8} x2={148} y2={H - 4} />
      <Note x={152} y={16} tone="muted" text="now" />
      <Zone x={148} y={38} w={RIGHT - 148} h={16} tone="muted" />
      <Level y={38} from={148} tone="sell" label="ask" />
      <line className="otx-level otx-stroke--buy" x1={148} y1={54} x2={RIGHT} y2={54} />
      <Note x={RIGHT} y={66} tone="buy" text="bid" anchor="end" />
      <Note x={200} y={50} tone="muted" text="spread" anchor="middle" />
      <Price d="M8,62 L28,56 L48,60 L68,48 L88,54 L108,44 L128,50 L148,46" />
      <Fill x={148} y={38} tone="buy" />
      <Fill x={148} y={54} tone="sell" />
    </>
  );
}

function StopArt() {
  return (
    <>
      <Level y={46} tone="stop" label="your stop" />
      <Price d="M8,20 L26,26 L44,22 L62,32 L80,28 L98,38 L116,40 L124,46 L136,58 L156,66 L176,62 L200,74 L226,70 L250,78" />
      <Trigger x={124} y={46} />
      <Fill x={136} y={58} tone="sell" />
    </>
  );
}

function StopLimitArt() {
  return (
    <>
      <Zone x={LEFT} y={56} w={RIGHT - LEFT} h={38} tone="sell" />
      <Note x={14} y={88} tone="sell" text="never fills below the limit" />
      <Level y={40} tone="stop" label="your stop" />
      <Level y={56} tone="limit" label="your limit" />
      <Price d="M8,16 L26,22 L44,18 L62,26 L80,24 L98,34 L108,40 L118,48 L134,62 L152,74 L172,70 L196,82 L222,78 L250,86" />
      <Trigger x={108} y={40} />
      <Fill x={118} y={48} tone="sell" />
    </>
  );
}

function TrailArt() {
  return (
    <>
      <path className="otx-level otx-level--trail otx-stroke--stop" d="M8,84 H28 V76 H68 V64 H108 V52 H148 V40 H250" />
      <Note x={112} y={76} tone="stop" text="stop only moves up" />
      <line className="otx-bracket otx-stroke--stop" x1={148} y1={27} x2={148} y2={39} />
      <Note x={143} y={24} tone="stop" text="Trail $" anchor="end" />
      <Price d="M8,70 L28,62 L48,66 L68,50 L88,54 L108,38 L128,42 L148,26 L168,34 L178,40" />
      <Price after d="M178,40 L188,46 L212,56 L232,60 L250,66" />
      <Trigger x={178} y={40} />
      <Fill x={188} y={46} tone="sell" />
    </>
  );
}

const ART: Readonly<Record<OrderExplainerKind, () => JSX.Element>> = {
  buy: BuyArt,
  sell: SellArt,
  LMT: LimitArt,
  MKT: MarketArt,
  STP: StopArt,
  'STP LMT': StopLimitArt,
  TRAIL: TrailArt,
};

export function OrderExplainerArt({ kind }: { kind: OrderExplainerKind }) {
  const Art = ART[kind];
  return (
    <svg
      className="otx-art"
      viewBox={`0 0 ${W} ${H}`}
      aria-hidden="true"
      focusable="false"
      data-testid={`order-explainer-art-${kind}`}
    >
      <Art />
    </svg>
  );
}
