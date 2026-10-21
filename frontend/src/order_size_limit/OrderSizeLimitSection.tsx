/**
 * Settings > Loss limits, under the daily loss limit (ADR 064): your order size limit -- Max shares and
 * Max risk at stop, one column each for Paper and Sim. The layout is the preview the operator chose on
 * 2026-10-20; an empty box is no limit, and every box starts empty. A box saves on Enter or when it is left.
 */
import { Info } from 'lucide-react';
import { useEffect, useState, type KeyboardEvent, type ReactNode } from 'react';
import { whyProps } from '../ux';
import {
  fetchOrderSizeLimit,
  saveOrderSizeLimit,
  type OrderSizeLimitField,
  type OrderSizeLimitPatch,
  type OrderSizeLimitSettings,
  type OrderSizeLimitVenue,
} from './orderSizeLimitApi';
import {
  ORDER_SIZE_LIMIT_BUSY_READING,
  ORDER_SIZE_LIMIT_BUSY_SAVING,
  ORDER_SIZE_LIMIT_EMPTY_NOTE,
  ORDER_SIZE_LIMIT_MAX_RISK_LABEL,
  ORDER_SIZE_LIMIT_MAX_RISK_TIP,
  ORDER_SIZE_LIMIT_MAX_SHARES_LABEL,
  ORDER_SIZE_LIMIT_MAX_SHARES_TIP,
  ORDER_SIZE_LIMIT_READ_FAILED,
  ORDER_SIZE_LIMIT_SAVE_FAILED,
  ORDER_SIZE_LIMIT_TIP,
  ORDER_SIZE_LIMIT_TITLE,
  ORDER_SIZE_LIMIT_UNREADABLE_NOTE,
  ORDER_SIZE_LIMIT_VENUE_NAMES,
  ORDER_SIZE_LIMIT_WHOLE_DOLLARS,
  ORDER_SIZE_LIMIT_WHOLE_SHARES,
} from './orderSizeLimitWords';
import './orderSizeLimit.css';

const VENUES: OrderSizeLimitVenue[] = ['paper', 'sim'];
const MAX = 1_000_000;

type Drafts = Record<OrderSizeLimitVenue, Record<OrderSizeLimitField, string>>;

const ROWS: { field: OrderSizeLimitField; label: string; tip: string; dollars: boolean; invalid: string }[] = [
  { field: 'max_shares', label: ORDER_SIZE_LIMIT_MAX_SHARES_LABEL, tip: ORDER_SIZE_LIMIT_MAX_SHARES_TIP, dollars: false,
    invalid: ORDER_SIZE_LIMIT_WHOLE_SHARES },
  { field: 'max_risk_usd', label: ORDER_SIZE_LIMIT_MAX_RISK_LABEL, tip: ORDER_SIZE_LIMIT_MAX_RISK_TIP, dollars: true,
    invalid: ORDER_SIZE_LIMIT_WHOLE_DOLLARS },
];

function Tip({ label, tip }: { label: ReactNode; tip: string }) {
  return (
    <span className="order-size-tip" tabIndex={0}>
      {label}
      <Info className="order-size-tip-icon" aria-hidden="true" size={14} />
      <span className="order-size-tip-text" role="tooltip">{tip}</span>
    </span>
  );
}

/** Empty is null (no limit); a whole number 1 to 1,000,000 is itself; anything else is undefined. */
export function parseLimit(raw: string): number | null | undefined {
  const cleaned = raw.replace(/[$,\s]/g, '');
  if (cleaned === '') return null;
  if (!/^\d+$/.test(cleaned)) return undefined;
  const value = Number(cleaned);
  return value >= 1 && value <= MAX ? value : undefined;
}

function draftsOf(settings: OrderSizeLimitSettings): Drafts {
  const text = (value: number | null) => (value == null ? '' : String(value));
  return {
    paper: { max_shares: text(settings.venues.paper.max_shares), max_risk_usd: text(settings.venues.paper.max_risk_usd) },
    sim: { max_shares: text(settings.venues.sim.max_shares), max_risk_usd: text(settings.venues.sim.max_risk_usd) },
  };
}

export function OrderSizeLimitSection() {
  const [settings, setSettings] = useState<OrderSizeLimitSettings | null>(null);
  const [drafts, setDrafts] = useState<Drafts | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    fetchOrderSizeLimit()
      .then((view) => {
        if (!live) return;
        setSettings(view.settings);
        setDrafts(draftsOf(view.settings));
      })
      .catch((e: unknown) => live && setError(`${ORDER_SIZE_LIMIT_READ_FAILED}: ${e instanceof Error ? e.message : e}`));
    return () => {
      live = false;
    };
  }, []);

  const save = async (patch: OrderSizeLimitPatch) => {
    setBusy(true);
    try {
      const view = await saveOrderSizeLimit(patch);
      setSettings(view.settings);
      setDrafts(draftsOf(view.settings));
      setError(null);
    } catch (e) {
      setError(`${ORDER_SIZE_LIMIT_SAVE_FAILED}: ${e instanceof Error ? e.message : e}`);
      if (settings) setDrafts(draftsOf(settings));
    } finally {
      setBusy(false);
    }
  };

  const commit = (venue: OrderSizeLimitVenue, field: OrderSizeLimitField, invalid: string) => {
    if (!settings || !drafts) return;
    const value = parseLimit(drafts[venue][field]);
    if (value === undefined) {
      setError(invalid);
      return;
    }
    // A file Nova could not use is replaced by any save, even of the box as it stands.
    if (value !== settings.venues[venue][field] || settings.source === 'unreadable') {
      void save({ [venue]: { [field]: value } });
    } else {
      setError(null);
    }
  };

  const locked = !settings || busy;
  const lockedWhy = !settings ? ORDER_SIZE_LIMIT_BUSY_READING : ORDER_SIZE_LIMIT_BUSY_SAVING;
  const unreadable = settings?.source === 'unreadable' ? `${settings.error}. ${ORDER_SIZE_LIMIT_UNREADABLE_NOTE}` : null;
  const shown = error ?? unreadable;

  const box = (venue: OrderSizeLimitVenue, row: (typeof ROWS)[number]) => {
    const id = `order-size-limit-${venue}-${row.field}`;
    const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') commit(venue, row.field, row.invalid);
    };
    return (
      <span className="order-size-box" key={id}>
        {/* The same slot on both rows, so the share and dollar boxes line up. */}
        <span className="order-size-note order-size-unit" aria-hidden="true">{row.dollars ? '$' : ''}</span>
        <input
          id={id}
          inputMode="numeric"
          aria-label={`${ORDER_SIZE_LIMIT_VENUE_NAMES[venue]} ${row.label}`}
          value={drafts ? drafts[venue][row.field] : ''}
          disabled={locked}
          {...whyProps(locked, lockedWhy)}
          onChange={(e) => {
            const text = e.target.value;
            setDrafts((d) => (d ? { ...d, [venue]: { ...d[venue], [row.field]: text } } : d));
          }}
          onBlur={() => commit(venue, row.field, row.invalid)}
          onKeyDown={onKey}
          aria-describedby={shown ? 'order-size-limit-error' : undefined}
        />
      </span>
    );
  };

  return (
    <section className="settings-block order-size-limit" data-testid="order-size-limit-settings">
      <div className="order-size-grid">
        <Tip label={<strong>{ORDER_SIZE_LIMIT_TITLE}</strong>} tip={ORDER_SIZE_LIMIT_TIP} />
        {VENUES.map((venue) => (
          <span className="order-size-venue" key={venue}>{ORDER_SIZE_LIMIT_VENUE_NAMES[venue]}</span>
        ))}
        {ROWS.map((row) => [
          <span className="order-size-label" key={`${row.field}-label`}>
            <Tip label={row.label} tip={row.tip} />
          </span>,
          ...VENUES.map((venue) => box(venue, row)),
        ])}
      </div>
      <span className="order-size-note">{ORDER_SIZE_LIMIT_EMPTY_NOTE}</span>
      {shown ? (
        <p className="order-size-error" id="order-size-limit-error" role="alert">{shown}</p>
      ) : null}
    </section>
  );
}
