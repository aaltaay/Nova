/**
 * What each futures and macro tile is, as a picture (operator ask 2026-10-14: "if it's gold, I want to see a gold
 * bar ... crude, a barrel"). Drawn here, inline, so the page loads no image; an unknown tile id draws nothing.
 */
import { useId } from 'react';

/** The four index futures: a badge with the index's short name. */
const BADGES: Record<string, { text: string; fill: string }> = {
  es: { text: 'S&P', fill: '#4f6fe0' },
  nq: { text: 'NDX', fill: '#1f93b8' },
  rty: { text: 'R2K', fill: '#8a55c4' },
  ym: { text: 'DOW', fill: '#2c8f63' },
};

function Badge({ text, fill }: { text: string; fill: string }) {
  return (
    <>
      <rect x={1} y={6} width={30} height={20} rx={5} fill={fill} />
      <text x={16} y={19.6} textAnchor="middle" fontSize={10} fontWeight={800} fill="#fff" letterSpacing={-0.2}
        fontFamily="system-ui, sans-serif">{text}</text>
    </>
  );
}

function GoldBar({ uid }: { uid: string }) {
  return (
    <>
      <defs>
        <linearGradient id={`${uid}-face`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#f6c945" />
          <stop offset="1" stopColor="#b8860b" />
        </linearGradient>
      </defs>
      <polygon points="9,9 23,9 26,14.5 6,14.5" fill="#ffe58a" />
      <polygon points="6,14.5 26,14.5 29,24 3,24" fill={`url(#${uid}-face)`} />
      <polygon points="3,24 29,24 29,25.5 3,25.5" fill="#8a6408" />
      <line x1={10} y1={17.5} x2={16} y2={17.5} stroke="#fff3c4" strokeWidth={1.2} strokeLinecap="round" opacity={0.8} />
    </>
  );
}

function OilBarrel({ uid }: { uid: string }) {
  return (
    <>
      <defs>
        <linearGradient id={`${uid}-drum`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#24548a" />
          <stop offset="0.45" stopColor="#4d86c6" />
          <stop offset="1" stopColor="#1d4573" />
        </linearGradient>
      </defs>
      <rect x={7} y={5} width={18} height={23} rx={2.5} fill={`url(#${uid}-drum)`} />
      <ellipse cx={16} cy={5.6} rx={9} ry={1.8} fill="#6d9fd6" />
      <line x1={7} y1={11} x2={25} y2={11} stroke="#163a63" strokeWidth={1.4} />
      <line x1={7} y1={22.5} x2={25} y2={22.5} stroke="#163a63" strokeWidth={1.4} />
      <path d="M16 12.8 C16 12.8 12.6 16.6 12.6 18.6 a3.4 3.4 0 0 0 6.8 0 C19.4 16.6 16 12.8 16 12.8Z" fill="#0d0d0f" />
      <circle cx={14.9} cy={18.4} r={0.9} fill="#5a5a60" />
    </>
  );
}

function Bitcoin() {
  return (
    <>
      <circle cx={16} cy={16} r={13} fill="#f7931a" />
      <text x={16.4} y={21.4} textAnchor="middle" fontSize={15} fontWeight={800} fill="#fff"
        fontFamily="system-ui, sans-serif">B</text>
      <rect x={14} y={7.4} width={1.6} height={3} fill="#fff" />
      <rect x={17.2} y={7.4} width={1.6} height={3} fill="#fff" />
      <rect x={14} y={21.6} width={1.6} height={3} fill="#fff" />
      <rect x={17.2} y={21.6} width={1.6} height={3} fill="#fff" />
    </>
  );
}

/** The VIX: a gauge, calm green to fearful red. */
function Gauge() {
  return (
    <>
      <path d="M5 22 A11 11 0 0 1 10.5 12.47" stroke="#30d158" strokeWidth={3.6} fill="none" />
      <path d="M10.5 12.47 A11 11 0 0 1 21.5 12.47" stroke="#ff9f0a" strokeWidth={3.6} fill="none" />
      <path d="M21.5 12.47 A11 11 0 0 1 27 22" stroke="#ff453a" strokeWidth={3.6} fill="none" />
      <line x1={16} y1={22} x2={19.2} y2={13.6} stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" />
      <circle cx={16} cy={22} r={2.2} fill="currentColor" />
    </>
  );
}

/** The 10-year yield: the Treasury. */
function Treasury() {
  return (
    <g fill="#9fb4d8">
      <polygon points="4,11 16,4.5 28,11" />
      <rect x={4} y={11.5} width={24} height={2} />
      {[6.5, 12, 17.5, 23].map((x) => <rect key={x} x={x} y={14.5} width={2.6} height={9} />)}
      <rect x={3} y={24.5} width={26} height={2.5} />
    </g>
  );
}

/** Small caps against the S&P: a balance, the small side up. */
function Balance() {
  return (
    <g stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" fill="none">
      <line x1={16} y1={6} x2={16} y2={26} />
      <line x1={11} y1={26} x2={21} y2={26} />
      <line x1={6} y1={11} x2={26} y2={8} />
      <path d="M3 17 L6 11 L9 17 Z" fill="#8a55c4" stroke="#8a55c4" />
      <path d="M22.5 14 L26 8 L29.5 14 Z" fill="#4f6fe0" stroke="#4f6fe0" />
    </g>
  );
}

export function TileIcon({ id }: { id: string }) {
  const uid = useId().replace(/:/g, '');
  const badge = BADGES[id];
  const body = badge ? <Badge {...badge} />
    : id === 'gc' ? <GoldBar uid={uid} />
      : id === 'cl' ? <OilBarrel uid={uid} />
        : id === 'btc' ? <Bitcoin />
          : id === 'vix' ? <Gauge />
            : id === 'tnx' ? <Treasury />
              : id === 'small_caps' ? <Balance />
                : null;
  if (!body) return null;
  return (
    <svg className="mk-tile__icon" viewBox="0 0 32 32" aria-hidden="true" data-testid={`market-icon-${id}`}>
      {body}
    </svg>
  );
}
