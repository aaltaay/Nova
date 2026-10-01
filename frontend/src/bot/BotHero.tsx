/**
 * The Bots page hero (approved mockup v4, ADR 042): the bot's state in one sentence,
 * the master level -- the most any setup may do on this venue -- as three segments,
 * every gate the backend checks as a chip in two groups (what Activate needs, what
 * each order still meets), one Activate, the kill switch, and the bot's trade.
 * Choosing a level never activates the bot. Activate is locked, with the reason,
 * until the backend would accept it; after a bot trip it asks first. Never "live"
 * on a practice venue.
 */
import { useState } from 'react';
import { writeNovaApiKey } from '../api/novaFetch';
import {
  BOT_ACTIVATE_LABEL,
  BOT_API_KEY_HINT,
  BOT_API_KEY_SAVE,
  BOT_DEACTIVATE_LABEL,
  BOT_LEVEL_BLURBS,
  BOT_LEVEL_HINTS,
  BOT_LEVEL_LABELS,
  BOT_STATE_ACTIVE,
  BOT_STATE_NOT_ACTIVE,
} from '../constantGroups/bot';
import {
  BOTS_ACTIVATE_READY,
  BOTS_ACTIVATE_WAITS_ON,
  BOTS_BUSY_WHY,
  BOTS_FIRE_WAITS_ON,
  BOTS_KEY_EMPTY_WHY,
  BOTS_MASTER_HEAD,
  BOTS_MASTER_TIP,
  BOTS_NOT_TRADING_NOW,
  BOTS_REENABLE_OK,
  BOTS_STALE_API,
} from '../constantGroups/bots_page';
import { useTradingPinGate } from '../ibkr/useTradingPinGate';
import { tipProps } from '../ux/hoverTip';
import { BotGateChips, type GateHandlers } from './BotGateChips';
import { closedGates, gateContext, gateLine, gateLines } from './botGateWords';
import { BotKillSwitch } from './BotKillSwitch';
import { strategySetups, setupNames } from './botLevels';
import { deactivatedLine, heroSentence, prose, sessionVenueName, stocksLine, tradeLine } from './botsPageFormat';
import type { BotArm } from './useBotArm';
import type { KillSwitchControl } from './useKillSwitch';

const LEVELS = [0, 1, 2] as const;

interface Props {
  /** The page's one useBotArm(). */
  arm: BotArm;
  killSwitch: KillSwitchControl;
  dayPnl: number | null;
  /** Gate chip actions the page owns (open a Level 2, scroll to the setups, focus the stock box). */
  onOpenL2: (symbol: string) => void;
  onShowSetups: () => void;
  onAddSymbol: () => void;
}

export function BotHero({ arm, killSwitch, dayPnl, onOpenL2, onShowSetups, onAddSymbol }: Props) {
  const { session, error, busy, stop, level, active, ready, lock, showKeyField, onLevel, onActivate } = arm;
  const [keyDraft, setKeyDraft] = useState('');
  const { ensureUnlocked, pinDialog } = useTradingPinGate();
  if (!session) return null;

  const venue = sessionVenueName(session);
  const ctx = gateContext(session, dayPnl);
  const gatesKnown = Array.isArray(session.gates);
  const chips = gateLines(session.gates, ctx);
  const fireWaits = closedGates(session.gates, 'fire').map(g => gateLine(g, ctx).text);
  const atStrategy = strategySetups(session);
  const off = deactivatedLine(session.deactivated);
  const notReadyWhy = session.ready_reason ?? session.runner?.reason ?? null;
  const trade = tradeLine(session.trade);
  const activateWhy = busy ? BOTS_BUSY_WHY : lock.why;
  const handlers: GateHandlers = {
    onUnlock: () => void ensureUnlocked(),
    onOpenL2,
    onShowSetups,
    onAddSymbol,
    onResetKill: () => void killSwitch.act(false),
  };

  return (
    <section
      className={`bots-hero${active && ready ? ' bots-hero--trading' : ''}${active ? ' bots-hero--armed' : ''}`}
      data-testid="bots-hero"
    >
      <div className="bots-hero__state">
        <div className="bots-hero__head">
          <span className={`bots-dot${active ? (ready ? ' bots-dot--on' : '') : level <= 0 ? ' bots-dot--off' : ''}`} aria-hidden="true" />
          <h2 data-testid="bots-hero-state">{active ? BOT_STATE_ACTIVE : BOT_STATE_NOT_ACTIVE}</h2>
        </div>
        {active && !ready ? (
          <p className="bots-hero__notready" data-testid="bots-hero-not-ready">
            {BOTS_NOT_TRADING_NOW}{notReadyWhy ? ` — ${prose(notReadyWhy)}` : ''}
          </p>
        ) : null}
        {!active && off ? <p className="bots-hero__off" data-testid="bots-hero-deactivated">{off}</p> : null}
        <p className="bots-hero__sentence" data-testid="bots-hero-sentence">{heroSentence(session)}</p>
        <p className="bots-hero__playing" data-testid="bots-hero-stocks">{stocksLine(session)}</p>
        {trade ? <p className="bots-hero__trade" data-testid="bots-hero-trade">{trade}</p> : null}
      </div>

      <div className="bots-hero__main">
        <span className="bots-hero__dialhead" {...tipProps(BOTS_MASTER_TIP, BOTS_MASTER_HEAD(venue))}>{BOTS_MASTER_HEAD(venue)}</span>
        <div className="bots-seg" role="radiogroup" aria-label={BOTS_MASTER_HEAD(venue)}>
          {LEVELS.map(n => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={level === n}
              aria-label={`L${n} ${BOT_LEVEL_LABELS[n]}: ${BOT_LEVEL_BLURBS[n]}`}
              className={`bots-seg__opt${level === n ? ' is-on' : ''}`}
              data-testid={`bots-level-${n}`}
              disabled={busy}
              data-why={busy ? BOTS_BUSY_WHY : undefined}
              {...(busy ? {} : tipProps(prose(BOT_LEVEL_HINTS[n]), `Master level ${BOT_LEVEL_LABELS[n]}`))}
              onClick={() => { if (level !== n) void onLevel(n); }}
            >
              <b><span className="bots-seg__lvl">L{n}</span>{BOT_LEVEL_LABELS[n]}</b>
              <small>{BOT_LEVEL_BLURBS[n]}</small>
            </button>
          ))}
        </div>
        <p className="bots-hero__atstrategy" data-testid="bots-hero-at-strategy">
          At Strategy: <b>{setupNames(atStrategy)}</b>
        </p>
        {gatesKnown ? (
          <BotGateChips gates={chips} handlers={handlers} />
        ) : (
          <p className="bots-hero__stale" role="status" data-testid="bots-gates-unreported">{BOTS_STALE_API}</p>
        )}
      </div>

      <div className="bots-hero__actions">
        {active ? (
          <button type="button" className="bots-btn bots-btn--block" data-testid="bots-stop" disabled={busy}
            data-why={busy ? BOTS_BUSY_WHY : undefined} onClick={() => void stop()}>
            ■ {BOT_DEACTIVATE_LABEL}
          </button>
        ) : (
          <button
            type="button"
            className="bots-btn bots-btn--primary bots-btn--block"
            data-testid="bots-activate"
            disabled={activateWhy != null}
            data-why={activateWhy ?? undefined}
            {...(activateWhy == null && lock.reenable ? tipProps(lock.reenable, BOTS_REENABLE_OK) : {})}
            onClick={() => { if (activateWhy == null) void onActivate(); }}
          >
            ▶ {lock.reenable && !lock.why ? BOTS_REENABLE_OK : `${BOT_ACTIVATE_LABEL} bot`}
          </button>
        )}
        {!active && gatesKnown ? (
          <p className="bots-hero__hint" data-testid="bots-activate-hint">
            {lock.waits.length ? `${BOTS_ACTIVATE_WAITS_ON}: ${lock.waits.join(' ')}` : lock.reenable ?? BOTS_ACTIVATE_READY}
          </p>
        ) : null}
        {gatesKnown && fireWaits.length ? (
          <p className="bots-hero__hint bots-hero__hint--fire" data-testid="bots-fire-hint">
            {BOTS_FIRE_WAITS_ON}: {fireWaits.join(' · ')}
          </p>
        ) : null}
        <BotKillSwitch killSwitch={killSwitch} />
        {error ? <p className="bots-hero__error" data-testid="bots-error" role="alert">{prose(error)}</p> : null}
        {showKeyField ? (
          <form
            className="bots-hero__key"
            data-testid="bots-api-key"
            onSubmit={e => { e.preventDefault(); writeNovaApiKey(keyDraft); setKeyDraft(''); }}
          >
            <input type="password" autoComplete="off" value={keyDraft} aria-label={BOT_API_KEY_HINT}
              placeholder={BOT_API_KEY_HINT} onChange={e => setKeyDraft(e.target.value)} />
            <button type="submit" className="bots-btn" disabled={!keyDraft.trim()}
              data-why={keyDraft.trim() ? undefined : BOTS_KEY_EMPTY_WHY}>{BOT_API_KEY_SAVE}</button>
          </form>
        ) : null}
      </div>
      {pinDialog}
    </section>
  );
}
