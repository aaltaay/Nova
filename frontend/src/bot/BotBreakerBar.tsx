/**
 * The loss breakers on one bar, the operator's to move (ADR 032; operator ask
 * 2026-09-24: "move that slider ... make sure these changes are persistent"):
 * drag the all-stop or the bot trip -- or focus one and use the arrow keys, $5 a
 * step -- and on release the desk venue's pair is saved in the bot session
 * (`PATCH /api/bot/session {breakers}`), so a restart keeps it. Loosening Live
 * asks first. A marker at today's day P&L shows how close the account is. An
 * API older than ADR 032 keeps the fixed -$50 / -$200 and says so.
 */
import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import {
  BOT_BREAKER_FIRED_NOTE,
  BOT_BREAKER_HARD_LABEL,
  BOT_BREAKER_HARD_TIP,
  BOT_BREAKER_HINT,
  BOT_BREAKER_LOOSEN_LIVE,
  BOT_BREAKER_LOOSEN_LIVE_OK,
  BOT_BREAKER_NOW_TIP,
  BOT_BREAKER_SOFT_LABEL,
  BOT_BREAKER_SOFT_TIP,
  BOT_HARD_BREAKER_USD,
  BOT_SOFT_BREAKER_USD,
} from '../constantGroups/bot';
import {
  BOTS_BREAKER_TODAY,
  BOTS_BREAKER_TODAY_UNKNOWN,
  BOTS_BREAKERS_CUSTOM,
  BOTS_BREAKERS_DEFAULTS,
  BOTS_BREAKERS_OLD_API,
  BOTS_BREAKERS_RESET,
  BOTS_BREAKERS_SAVING,
  BOTS_BREAKERS_TITLE,
  BOTS_BREAKERS_VENUE,
  BOTS_BUSY_WHY,
  BOTS_SLIDER_COMMIT_MS,
  BOTS_VENUE_NAMES,
} from '../constantGroups/bots_page';
import { confirmApp } from '../ux/appDialogApi';
import { tipProps } from '../ux/hoverTip';
import { fmtUsd, fmtUsdCents } from './botsPageFormat';
import {
  breakerFloor,
  breakerLimits,
  breakerPct,
  clamp,
  markerRange,
  valueAt,
  type BreakerKey,
} from './breakerScale';
import type { BotBreakers } from './types';

type Patch = (body: Record<string, unknown>) => Promise<unknown>;

interface Props {
  breakers: BotBreakers | undefined;
  dayPnl: number | null;
  busy: boolean;
  patch: Patch;
}

const NAMES: Record<BreakerKey, string> = { soft: BOT_BREAKER_SOFT_LABEL, hard: BOT_BREAKER_HARD_LABEL };
const TIPS: Record<BreakerKey, string> = { soft: BOT_BREAKER_SOFT_TIP, hard: BOT_BREAKER_HARD_TIP };

export function BotBreakerBar({ breakers, dayPnl, busy, patch }: Props) {
  const lim = breakerLimits(breakers);
  const movable = breakers != null;
  const [draft, setDraft] = useState({ soft: lim.soft, hard: lim.hard });
  const [saving, setSaving] = useState(false);
  const moving = useRef<{ key: BreakerKey; floor: number } | null>(null);
  const keyTimer = useRef<number | null>(null);
  const bar = useRef<HTMLDivElement>(null);
  const floorRef = useRef(breakerFloor(lim.hard, dayPnl));

  // A new session value (another window, the backend's snap) wins unless a drag is in flight.
  useEffect(() => {
    if (!moving.current && keyTimer.current == null) setDraft({ soft: lim.soft, hard: lim.hard });
  }, [lim.soft, lim.hard]);
  useEffect(() => () => {
    if (keyTimer.current != null) window.clearTimeout(keyTimer.current);
  }, []);

  // The bar's scale holds still while a marker moves, so the marker never runs from the pointer.
  if (!moving.current) floorRef.current = breakerFloor(Math.min(draft.hard, lim.hard), dayPnl);
  const floor = floorRef.current;
  const venue = breakers?.venue ?? null;
  const venueName = venue ? BOTS_VENUE_NAMES[venue] ?? venue : '';
  // A save in flight never locks the markers (the next drag simply saves after it), so no
  // why-tip flickers under the pointer on every release; only an API without breakers does.
  const locked = !movable ? BOTS_BREAKERS_OLD_API : null;
  const resetWhy = busy || saving ? BOTS_BUSY_WHY : null;
  const tone = dayPnl == null ? '' : dayPnl <= draft.soft ? ' is-bad' : dayPnl < 0 ? ' is-warn' : ' is-ok';

  async function commit(key: BreakerKey, value: number) {
    const before = key === 'soft' ? lim.soft : lim.hard;
    if (!breakers || value === before) return;
    const reset = () => setDraft({ soft: lim.soft, hard: lim.hard });
    if (venue === 'live' && value < before) {
      const ok = await confirmApp({
        title: `Loosen Live's ${NAMES[key].toLowerCase()}`,
        message: BOT_BREAKER_LOOSEN_LIVE(NAMES[key].toLowerCase(), fmtUsd(before), fmtUsd(value)),
        confirmLabel: BOT_BREAKER_LOOSEN_LIVE_OK,
        cancelLabel: `Keep ${fmtUsd(before)}`,
        tone: 'danger',
      });
      if (!ok) {
        reset();
        return;
      }
    }
    setSaving(true);
    try {
      const saved = await patch({ breakers: { venue, [`${key}_usd`]: value } });
      if (!saved) reset();
    } finally {
      setSaving(false);
    }
  }

  function rangeOf(key: BreakerKey): [number, number] {
    return markerRange(key, lim, key === 'soft' ? draft.hard : draft.soft);
  }

  function fromPointer(e: PointerEvent, key: BreakerKey, scale: number): number {
    const rect = bar.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0) return draft[key];
    return valueAt((e.clientX - rect.left) / rect.width, scale, lim.step, rangeOf(key));
  }

  function onPointerDown(e: PointerEvent<HTMLDivElement>, key: BreakerKey) {
    if (locked || (e.button ?? 0) !== 0) return;
    e.preventDefault();
    try {
      e.currentTarget.setPointerCapture?.(e.pointerId);
    } catch {
      // A pointer the browser no longer tracks: the drag still follows this element's own events.
    }
    e.currentTarget.focus();
    moving.current = { key, floor };
  }

  function onPointerMove(e: PointerEvent<HTMLDivElement>, key: BreakerKey) {
    const m = moving.current;
    if (!m || m.key !== key) return;
    const v = fromPointer(e, key, m.floor);
    if (v !== draft[key]) setDraft(d => ({ ...d, [key]: v }));
  }

  function onPointerUp(e: PointerEvent<HTMLDivElement>, key: BreakerKey) {
    const m = moving.current;
    if (!m || m.key !== key) return;
    try {
      e.currentTarget.releasePointerCapture?.(e.pointerId);
    } catch {
      // Already released (the pointer left the window): nothing to let go of.
    }
    const v = fromPointer(e, key, m.floor);
    moving.current = null;
    setDraft(d => ({ ...d, [key]: v }));
    void commit(key, v);
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>, key: BreakerKey) {
    if (locked) return;
    const range = rangeOf(key);
    const steps: Record<string, number> = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1, PageDown: -10, PageUp: 10 };
    let next: number | null = null;
    if (e.key in steps) next = clamp(draft[key] + steps[e.key] * lim.step, range);
    else if (e.key === 'Home') next = range[0];
    else if (e.key === 'End') next = range[1];
    if (next == null) return;
    e.preventDefault();
    const value = next;
    setDraft(d => ({ ...d, [key]: value }));
    if (keyTimer.current != null) window.clearTimeout(keyTimer.current);
    keyTimer.current = window.setTimeout(() => {
      keyTimer.current = null;
      void commit(key, value);
    }, BOTS_SLIDER_COMMIT_MS);
  }

  async function resetPair() {
    if (!breakers) return;
    const loosens = BOT_SOFT_BREAKER_USD < lim.soft || BOT_HARD_BREAKER_USD < lim.hard;
    if (venue === 'live' && loosens) {
      const ok = await confirmApp({
        title: 'Loosen Live\'s breakers',
        message: BOT_BREAKER_LOOSEN_LIVE('breakers', `${fmtUsd(lim.soft)} / ${fmtUsd(lim.hard)}`,
          `${fmtUsd(BOT_SOFT_BREAKER_USD)} / ${fmtUsd(BOT_HARD_BREAKER_USD)}`),
        confirmLabel: BOT_BREAKER_LOOSEN_LIVE_OK,
        tone: 'danger',
      });
      if (!ok) return;
    }
    setSaving(true);
    try {
      await patch({ breakers: { venue, soft_usd: BOT_SOFT_BREAKER_USD, hard_usd: BOT_HARD_BREAKER_USD } });
    } finally {
      setSaving(false);
    }
  }

  const knob = (key: BreakerKey) => {
    const range = rangeOf(key);
    return (
      <div
        role="slider"
        tabIndex={locked ? -1 : 0}
        aria-label={NAMES[key]}
        aria-valuemin={range[0]}
        aria-valuemax={range[1]}
        aria-valuenow={draft[key]}
        aria-valuetext={fmtUsd(draft[key])}
        aria-disabled={locked ? 'true' : undefined}
        data-why={locked ?? undefined}
        data-testid={`bots-breaker-${key}`}
        className={`bots-breakers__knob bots-breakers__knob--${key}`}
        style={{ left: `${breakerPct(draft[key], floor)}%` }}
        {...(locked ? {} : tipProps(TIPS[key], `${NAMES[key]} · ${fmtUsd(draft[key])}`))}
        onPointerDown={e => onPointerDown(e, key)}
        onPointerMove={e => onPointerMove(e, key)}
        onPointerUp={e => onPointerUp(e, key)}
        onPointerCancel={() => { moving.current = null; setDraft({ soft: lim.soft, hard: lim.hard }); }}
        onKeyDown={e => onKeyDown(e, key)}
      />
    );
  };

  const hardPct = breakerPct(draft.hard, floor);
  const softPct = breakerPct(draft.soft, floor);
  const custom = breakers?.custom === true;
  return (
    <div className="bots-breakers" data-testid="bot-strategy-breakers">
      <div className="bots-breakers__head">
        <span {...tipProps(`${BOT_BREAKER_HINT}\n${BOT_BREAKER_FIRED_NOTE}`, BOTS_BREAKERS_TITLE)}>{BOTS_BREAKERS_TITLE}</span>
        <span className="bots-breakers__lock" data-testid="bots-breakers-venue">
          {!movable ? BOTS_BREAKERS_OLD_API : saving ? BOTS_BREAKERS_SAVING
            : `${BOTS_BREAKERS_VENUE(venueName)} · ${custom ? BOTS_BREAKERS_CUSTOM : BOTS_BREAKERS_DEFAULTS}`}
        </span>
      </div>
      <div className="bots-breakers__bar" ref={bar}>
        <i className="bots-breakers__zone bots-breakers__zone--hard" style={{ left: 0, width: `${hardPct}%` }} aria-hidden="true" />
        <i className="bots-breakers__zone bots-breakers__zone--soft"
          style={{ left: `${hardPct}%`, width: `${Math.max(0, softPct - hardPct)}%` }} aria-hidden="true" />
        {knob('hard')}
        {knob('soft')}
        {dayPnl != null ? (
          <i className={`bots-breakers__now${tone}`} data-testid="bots-breaker-now" style={{ left: `${breakerPct(dayPnl, floor)}%` }}
            {...tipProps(BOT_BREAKER_NOW_TIP, `Today ${fmtUsdCents(dayPnl)}`)} />
        ) : null}
      </div>
      <div className="bots-breakers__labels">
        <span className="bots-breakers__lbl" style={{ left: `${hardPct}%` }} data-testid="bots-breaker-hard-label">
          <b className="is-bad">{fmtUsd(draft.hard)}</b> all-stop
        </span>
        <span className="bots-breakers__lbl" style={{ left: `${softPct}%` }} data-testid="bots-breaker-soft-label">
          <b className="is-warn">{fmtUsd(draft.soft)}</b> bot trip
        </span>
      </div>
      <div className="bots-breakers__foot">
        <span className={`bots-breakers__today${tone}`} data-testid="bots-breaker-today">
          {dayPnl == null ? BOTS_BREAKER_TODAY_UNKNOWN : <><b>{fmtUsdCents(dayPnl)}</b> {BOTS_BREAKER_TODAY}</>}
        </span>
        {movable && custom ? (
          <button type="button" className="bots-linkbtn" data-testid="bots-breakers-reset"
            disabled={resetWhy != null} data-why={resetWhy ?? undefined}
            onClick={() => void resetPair()}>
            {BOTS_BREAKERS_RESET}
          </button>
        ) : null}
      </div>
    </div>
  );

}
