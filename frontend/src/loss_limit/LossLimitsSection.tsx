/**
 * Settings > Loss limits (ADR 056): one daily loss limit in dollars and three checkboxes, for every
 * account and for you and the bots alike. The form is the approved mockup (v4, 2026-10-15): two
 * words a row, and the rule in a hover tip. Each change saves at once; the dollars save on Enter or
 * when the field is left.
 */
import { Info } from 'lucide-react';
import { useEffect, useState, type KeyboardEvent, type ReactNode } from 'react';
import { whyProps } from '../ux';
import { fetchLossLimit, saveLossLimit, type LossLimitPatch, type LossLimitSettings } from './lossLimitApi';
import {
  LOSS_LIMIT_AUTO_SELL_LABEL,
  LOSS_LIMIT_AUTO_SELL_NOTE,
  LOSS_LIMIT_AUTO_SELL_TIP,
  LOSS_LIMIT_BUSY_READING,
  LOSS_LIMIT_BUSY_SAVING,
  LOSS_LIMIT_DAILY_LABEL,
  LOSS_LIMIT_DAILY_TIP,
  LOSS_LIMIT_NO_NEW_BUYS_LABEL,
  LOSS_LIMIT_NO_NEW_BUYS_TIP,
  LOSS_LIMIT_READ_FAILED,
  LOSS_LIMIT_SAVE_FAILED,
  LOSS_LIMIT_WARN_LABEL,
  LOSS_LIMIT_WARN_TIP,
  LOSS_LIMIT_WHOLE_DOLLARS,
} from './lossLimitWords';
import './lossLimits.css';

const MIN_USD = 10;
const MAX_USD = 1_000_000;

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
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    fetchLossLimit()
      .then((view) => {
        if (!live) return;
        setSettings(view.settings);
        setDraft(String(view.settings.limit_usd));
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
      setDraft(String(view.settings.limit_usd));
      setError(null);
    } catch (e) {
      setError(`${LOSS_LIMIT_SAVE_FAILED}: ${e instanceof Error ? e.message : e}`);
      if (settings) setDraft(String(settings.limit_usd));
    } finally {
      setBusy(false);
    }
  };

  const commitLimit = () => {
    if (!settings) return;
    const value = parseLimitUsd(draft);
    if (value == null) {
      setError(LOSS_LIMIT_WHOLE_DOLLARS);
      return;
    }
    if (value !== settings.limit_usd) void save({ limit_usd: value });
    else setError(null);
  };

  const locked = !settings || busy;
  const lockedWhy = !settings ? LOSS_LIMIT_BUSY_READING : LOSS_LIMIT_BUSY_SAVING;

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') commitLimit();
  };

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
      <div className="loss-limit-row">
        <label htmlFor="loss-limit-usd">
          <Tip label={LOSS_LIMIT_DAILY_LABEL} tip={LOSS_LIMIT_DAILY_TIP} />
        </label>
        <span className="loss-limit-dollars">
          <span className="loss-limit-note">$</span>
          <input
            id="loss-limit-usd"
            inputMode="numeric"
            value={draft}
            disabled={locked}
            {...whyProps(locked, lockedWhy)}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commitLimit}
            onKeyDown={onKey}
            aria-describedby={error ? 'loss-limit-error' : undefined}
          />
        </span>
      </div>
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
