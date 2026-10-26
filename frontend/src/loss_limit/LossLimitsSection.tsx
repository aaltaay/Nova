/**
 * Settings > Loss limits (ADR 056, ADR 061): three dollar lines and three checkboxes, for every account.
 * The daily loss limit counts yours and the bots' trades together; Your trades and Bots' trades each
 * count one side's, and an empty box is no line for that side (operator decisions 2026-10-20). The
 * checkboxes apply to every line. The form is the approved mockup (v4, 2026-10-15) with the two side
 * rows under the limit: two words a row, and the rule in a hover tip. Each change saves at once; the
 * dollars save on Enter or when the field is left.
 */
import { Info } from 'lucide-react';
import { useEffect, useState, type KeyboardEvent, type ReactNode } from 'react';
import { whyProps } from '../ux';
import { fetchLossLimit, saveLossLimit, type LossLimitPatch, type LossLimitSettings } from './lossLimitApi';
import {
  LOSS_LIMIT_AUTO_SELL_LABEL,
  LOSS_LIMIT_AUTO_SELL_NOTE,
  LOSS_LIMIT_AUTO_SELL_TIP,
  LOSS_LIMIT_BOTS_LABEL,
  LOSS_LIMIT_BOTS_TIP,
  LOSS_LIMIT_BUSY_READING,
  LOSS_LIMIT_BUSY_SAVING,
  LOSS_LIMIT_DAILY_LABEL,
  LOSS_LIMIT_DAILY_TIP,
  LOSS_LIMIT_NO_NEW_BUYS_LABEL,
  LOSS_LIMIT_NO_NEW_BUYS_TIP,
  LOSS_LIMIT_OFF_PLACEHOLDER,
  LOSS_LIMIT_READ_FAILED,
  LOSS_LIMIT_SAVE_FAILED,
  LOSS_LIMIT_WARN_LABEL,
  LOSS_LIMIT_WARN_TIP,
  LOSS_LIMIT_WHOLE_DOLLARS,
  LOSS_LIMIT_WHOLE_DOLLARS_OR_OFF,
  LOSS_LIMIT_YOU_LABEL,
  LOSS_LIMIT_YOU_TIP,
} from './lossLimitWords';
import './lossLimits.css';

const MIN_USD = 10;
const MAX_USD = 1_000_000;

/** The three dollar lines: the account's (always set), then each side's (empty: no line). */
type LineKey = 'limit_usd' | 'you_usd' | 'bots_usd';
interface LineRow { key: LineKey; id: string; label: string; tip: string; optional: boolean }
const LINE_ROWS: LineRow[] = [
  { key: 'limit_usd', id: 'loss-limit-usd', label: LOSS_LIMIT_DAILY_LABEL, tip: LOSS_LIMIT_DAILY_TIP, optional: false },
  { key: 'you_usd', id: 'loss-limit-you-usd', label: LOSS_LIMIT_YOU_LABEL, tip: LOSS_LIMIT_YOU_TIP, optional: true },
  { key: 'bots_usd', id: 'loss-limit-bots-usd', label: LOSS_LIMIT_BOTS_LABEL, tip: LOSS_LIMIT_BOTS_TIP, optional: true },
];
type Drafts = Record<LineKey, string>;

function draftsOf(settings: LossLimitSettings): Drafts {
  const text = (value: number | null | undefined) => (value == null ? '' : String(value));
  return { limit_usd: text(settings.limit_usd), you_usd: text(settings.you_usd), bots_usd: text(settings.bots_usd) };
}

function Tip({ label, tip, children }: { label: ReactNode; tip: string; children?: ReactNode }) {
  return (
    <span className="loss-limit-tip" tabIndex={0}>
      {label}
      <Info className="loss-limit-tip-icon" aria-hidden="true" size={14} />
      <span className="loss-limit-tip-text" role="tooltip">{tip}</span>
      {children}
    </span>
  );
}

/** Whole dollars in range, or null. */
export function parseLimitUsd(raw: string): number | null {
  const cleaned = raw.replace(/[$,\s]/g, '');
  if (!/^\d+$/.test(cleaned)) return null;
  const value = Number(cleaned);
  return value >= MIN_USD && value <= MAX_USD ? value : null;
}

export function LossLimitsSection() {
  const [settings, setSettings] = useState<LossLimitSettings | null>(null);
  const [drafts, setDrafts] = useState<Drafts>({ limit_usd: '', you_usd: '', bots_usd: '' });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    fetchLossLimit()
      .then((view) => {
        if (!live) return;
        setSettings(view.settings);
        setDrafts(draftsOf(view.settings));
        setError(view.settings.error);
      })
      .catch((e: unknown) => live && setError(`${LOSS_LIMIT_READ_FAILED}: ${e instanceof Error ? e.message : e}`));
    return () => {
      live = false;
    };
  }, []);

  const save = async (patch: LossLimitPatch) => {
    setBusy(true);
    try {
      const view = await saveLossLimit(patch);
      setSettings(view.settings);
      setDrafts(draftsOf(view.settings));
      setError(null);
    } catch (e) {
      setError(`${LOSS_LIMIT_SAVE_FAILED}: ${e instanceof Error ? e.message : e}`);
      if (settings) setDrafts(draftsOf(settings));
    } finally {
      setBusy(false);
    }
  };

  /** A side line's empty box saves as no line; the daily loss limit always has dollars. */
  const commitLine = ({ key, optional }: LineRow) => {
    if (!settings) return;
    const raw = drafts[key];
    const off = optional && raw.trim() === '';
    const value = off ? null : parseLimitUsd(raw);
    if (!off && value == null) {
      setError(optional ? LOSS_LIMIT_WHOLE_DOLLARS_OR_OFF : LOSS_LIMIT_WHOLE_DOLLARS);
      return;
    }
    if (value !== (settings[key] ?? null)) void save({ [key]: value });
    else setError(null);
  };

  const locked = !settings || busy;
  const lockedWhy = !settings ? LOSS_LIMIT_BUSY_READING : LOSS_LIMIT_BUSY_SAVING;

  const dollarRow = (row: LineRow) => (
    <div className="loss-limit-row" key={row.key}>
      <label htmlFor={row.id}>
        <Tip label={row.label} tip={row.tip} />
      </label>
      <span className="loss-limit-dollars">
        <span className="loss-limit-note">$</span>
        <input
          id={row.id}
          inputMode="numeric"
          value={drafts[row.key]}
          placeholder={row.optional ? LOSS_LIMIT_OFF_PLACEHOLDER : undefined}
          disabled={locked}
          {...whyProps(locked, lockedWhy)}
          onChange={(e) => {
            const value = e.target.value;
            setDrafts((d) => ({ ...d, [row.key]: value }));
          }}
          onBlur={() => commitLine(row)}
          onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => {
            if (e.key === 'Enter') commitLine(row);
          }}
          aria-describedby={error ? 'loss-limit-error' : undefined}
        />
      </span>
    </div>
  );

  const check = (key: 'warn' | 'no_new_buys' | 'auto_sell', label: string, tip: string, note?: string) => (
    <label className="loss-limit-check" htmlFor={`loss-limit-${key}`}>
      <input
        id={`loss-limit-${key}`}
        type="checkbox"
        checked={settings ? settings[key] : false}
        disabled={locked}
        {...whyProps(locked, lockedWhy)}
        onChange={(e) => {
          const patch: LossLimitPatch = {};
          patch[key] = e.target.checked;
          void save(patch);
        }}
      />
      <Tip label={key === 'auto_sell' ? <strong>{label}</strong> : label} tip={tip} />
      {note ? <span className="loss-limit-note">{note}</span> : null}
    </label>
  );

  return (
    <section className="settings-block loss-limits" data-testid="loss-limits-settings">
      {LINE_ROWS.map(dollarRow)}
      <div className="loss-limit-rule" />
      {check('warn', LOSS_LIMIT_WARN_LABEL, LOSS_LIMIT_WARN_TIP)}
      {check('no_new_buys', LOSS_LIMIT_NO_NEW_BUYS_LABEL, LOSS_LIMIT_NO_NEW_BUYS_TIP)}
      {check('auto_sell', LOSS_LIMIT_AUTO_SELL_LABEL, LOSS_LIMIT_AUTO_SELL_TIP, LOSS_LIMIT_AUTO_SELL_NOTE)}
      {error ? (
        <p className="loss-limit-error" id="loss-limit-error" role="alert">{error}</p>
      ) : null}
    </section>
  );
}
