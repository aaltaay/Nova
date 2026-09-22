/**
 * Small shared pieces of the Account page: the `est` chip every practice
 * price wears, the share ring, the panel header, tone classes and ET time.
 */
import type { ReactNode } from 'react';
import { ACCOUNT_EST_CHIP, ACCOUNT_EST_TITLE } from '../constantGroups/account_page';
import { JOURNAL_CALENDAR_TIMEZONE } from '../constantGroups/market_ui';
import { formatSignedMoney } from '../components/globalBarMoney';
import { formatMoney } from '../utils/formatMoney';

export type Tone = 'up' | 'down' | 'flat' | 'bot' | 'muted';

export function toneOf(n: number | null | undefined): Tone {
  if (n == null || !Number.isFinite(n) || n === 0) return 'flat';
  return n > 0 ? 'up' : 'down';
}

export const toneClass = (tone: Tone): string => `acct-tone--${tone}`;

export function EstChip() {
  return (
    <span className="acct-est" title={ACCOUNT_EST_TITLE} data-testid="acct-est">
      {ACCOUNT_EST_CHIP}
    </span>
  );
}

/** Money cell: signed P&L in its tone, or a plain figure. */
export function Money({ value, signed = false, decimals = 2 }: { value: number | null | undefined; signed?: boolean; decimals?: number }) {
  const tone = signed ? toneOf(value) : 'flat';
  return (
    <span className={`acct-num ${signed ? toneClass(tone) : ''}`.trim()}>
      {signed ? formatSignedMoney(value, decimals) : formatMoney(value, decimals)}
    </span>
  );
}

interface RingProps {
  /** 0..1 share of the ring. */
  share: number;
  tone: Tone;
  size?: number;
  label?: string;
  testId?: string;
}

/** A share ring with its percent in the middle; a zero share draws the track only. */
export function Ring({ share, tone, size = 42, label, testId }: RingProps) {
  const r = size * 0.4;
  const w = Math.max(4, size * 0.11);
  const c = 2 * Math.PI * r;
  const m = size / 2;
  const clamped = Math.max(0, Math.min(1, Number.isFinite(share) ? share : 0));
  const pct = Math.round(clamped * 100);
  return (
    <svg
      className={`acct-ring ${toneClass(tone)}`}
      viewBox={`0 0 ${size} ${size}`}
      width={size}
      height={size}
      role="img"
      aria-label={label ?? `${pct}%`}
      data-testid={testId}
      data-share={clamped.toFixed(3)}
    >
      <circle className="acct-ring__track" cx={m} cy={m} r={r} fill="none" strokeWidth={w} />
      {clamped > 0 && (
        <circle
          className="acct-ring__arc"
          cx={m}
          cy={m}
          r={r}
          fill="none"
          strokeWidth={w}
          strokeLinecap="round"
          strokeDasharray={`${Math.max(1.5, c * clamped)} ${c}`}
          transform={`rotate(-90 ${m} ${m})`}
        />
      )}
      <text
        className={`acct-ring__pct${clamped > 0 ? '' : ' is-zero'}`}
        x={m}
        y={m + size * 0.085}
        textAnchor="middle"
        fontSize={size * 0.24}
        fontWeight={600}
      >
        {pct}%
      </text>
    </svg>
  );
}

export function PanelHead({ title, children, tabs }: { title?: string; tabs?: ReactNode; children?: ReactNode }) {
  return (
    <div className="acct-panel__head">
      {title && <h2 className="acct-panel__title">{title}</h2>}
      {tabs}
      {children && <div className="acct-panel__tools">{children}</div>}
    </div>
  );
}

const ET_TIME = new Intl.DateTimeFormat('en-GB', {
  timeZone: JOURNAL_CALENDAR_TIMEZONE,
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});
const ET_DATE = new Intl.DateTimeFormat('en-CA', {
  timeZone: JOURNAL_CALENDAR_TIMEZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

/** `HH:mm:ss` ET of epoch seconds. */
export function etTime(ts: number | null | undefined): string {
  if (ts == null || !Number.isFinite(ts)) return '—';
  return ET_TIME.format(new Date(ts * 1000));
}

/** `YYYY-MM-DD HH:mm:ss` ET of epoch seconds. */
export function etDateTime(ts: number | null | undefined): string {
  if (ts == null || !Number.isFinite(ts)) return '—';
  const at = new Date(ts * 1000);
  return `${ET_DATE.format(at)} ${ET_TIME.format(at)}`;
}

/** `HH:mm:ss` ET of an ISO timestamp (IBKR order rows). */
export function etTimeIso(iso: string | null | undefined): string {
  if (!iso) return '—';
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ET_TIME.format(new Date(ms)) : '—';
}

/** Short `Mon D` ET label of an ISO timestamp, for "since reset (Sep 18)". */
export function etShortDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return null;
  return new Intl.DateTimeFormat('en-US', { timeZone: JOURNAL_CALENDAR_TIMEZONE, month: 'short', day: 'numeric' }).format(new Date(ms));
}

/** `YYYY-MM-DD HH:mm` ET of an ISO timestamp. */
export function etDateTimeIso(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return null;
  const at = new Date(ms);
  return `${ET_DATE.format(at)} ${ET_TIME.format(at).slice(0, 5)}`;
}
