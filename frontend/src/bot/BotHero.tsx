/**
 * The Bots page hero (approved mockup v4, ADR 027): the bot's state in one
 * sentence, the chosen setup's level as three segments (ADR 031), every gate the
 * backend checks as a chip that can open itself, Activate / the kill switch, and
 * the bot's trade (ADR 030). Level 2 arms first; Activate at Strategy waits on the
 * chosen setup's read-out on Live only.
 */
import { useState } from 'react';
import { writeNovaApiKey } from '../api/novaFetch';
import {
  BOT_ACTIVATE_LABEL,
  BOT_API_KEY_HINT,
  BOT_API_KEY_SAVE,
  BOT_DEACTIVATE_LABEL,
  BOT_GATE_LABELS,
  BOT_LEVEL_BLURBS,
  BOT_LEVEL_LABELS,
  BOT_STATE_ACTIVE,
  BOT_STATE_NOT_ACTIVE,
} from '../constantGroups/bot';
import {
  BOTS_ACTIVATE_WAITS_ON,
  BOTS_BUSY_WHY,
  BOTS_IN_CONTROL_LABEL,
  BOTS_KEY_EMPTY_WHY,
  BOTS_KILL_BUSY_WHY,
  BOTS_KILL_UNREAD_WHY,
  BOTS_KILL_RESET_LABEL,
  BOTS_KILL_TRIP_LABEL,
  BOTS_KILL_TRIP_NOTE,
  BOTS_KILL_TRIPPED_NOTE,
  BOTS_STALE_API,
} from '../constantGroups/bots_page';
import { useTradingPinGate } from '../ibkr/useTradingPinGate';
import { BotGateChips, type GateHandlers } from './BotGateChips';
import { closedActivateGates, gateContext, gateLines, heroSentence, playingLine, prose, tradeLine } from './botsPageFormat';
import type { BotArm } from './useBotArm';
import type { KillSwitchControl } from './useKillSwitch';

const LEVELS = [0, 1, 2] as const;

interface Props {
  /** The page's one useBotArm() (its padlock watcher must run once). */
  arm: BotArm;
  killSwitch: KillSwitchControl;
  dayPnl: number | null;
  /** Gate chip actions the page owns (open a Level 2, scroll to the read-out, focus the symbol box). */
  onOpenL2: (symbol: string) => void;
  onReadout: () => void;
  onAddSymbol: () => void;
}

export function BotHero({ arm, killSwitch, dayPnl, onOpenL2, onReadout, onAddSymbol }: Props) {
  const {
    session, error, busy, stop, armed, level, display, live, activateBlocked, activateReason,
    showKeyField, onLevel, onControl, activate, gate,
  } = arm;
  const [keyDraft, setKeyDraft] = useState('');
  const { ensureUnlocked, pinDialog } = useTradingPinGate();
  if (!session) return null;

  const gatesKnown = Array.isArray(session.gates);
  const chips = gateLines(session.gates, gateContext(session, dayPnl, gate.blockers));
  const waitsOn = closedActivateGates(session.gates).map(g => BOT_GATE_LABELS[g.id] ?? g.id);
  const clamped = (level > 2 ? 2 : level) as 0 | 1 | 2;
  const headline = display.looksActive ? BOT_STATE_ACTIVE : armed ? display.label : BOT_STATE_NOT_ACTIVE;
  const sentence = heroSentence(session);
  const playing = playingLine(session);
  const trade = tradeLine(session.trade);
  const tripped = killSwitch.status?.tripped === true;
  const handlers: GateHandlers = {
    onUnlock: () => void ensureUnlocked(),
    onOpenL2,
    onReadout,
    onAddSymbol,
    onResetKill: () => void killSwitch.act(false),
  };

  return (
    <section
      className={`bots-hero${live ? ' bots-hero--live' : ''}${display.looksActive ? ' bots-hero--armed' : ''}`}
      data-testid="bots-hero"
    >
      <div className="bots-hero__state">
        <div className="bots-hero__head">
          <span className={`bots-dot${display.looksActive ? ' bots-dot--on' : level <= 0 ? ' bots-dot--off' : ''}`} aria-hidden="true" />
          <h2 data-testid="bots-hero-state">{headline}</h2>
        </div>
        <p className="bots-hero__sentence" data-testid="bots-hero-sentence">
          {sentence.lead}{sentence.count ? <b>{sentence.count}</b> : null}{sentence.tail}
        </p>
        <p className="bots-hero__playing" data-testid="bots-hero-playing">Playing <b>{playing.setup}</b>{playing.rest}</p>
        {trade ? <p className="bots-hero__trade" data-testid="bots-hero-trade">{trade}</p> : null}
      </div>

      <div className="bots-hero__main">
        <div className="bots-seg" role="radiogroup" aria-label="Level">
          {LEVELS.map(n => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={clamped === n}
              aria-label={`L${n} ${BOT_LEVEL_LABELS[n]}: ${BOT_LEVEL_BLURBS[n]}`}
              className={`bots-seg__opt${clamped === n ? ' is-on' : ''}`}
              data-testid={`bots-level-${n}`}
              disabled={busy}
              data-why={busy ? BOTS_BUSY_WHY : undefined}
              onClick={() => { if (clamped !== n) void onLevel(n); }}
            >
              <b><span className="bots-seg__lvl">L{n}</span>{BOT_LEVEL_LABELS[n]}</b>
              <small>{BOT_LEVEL_BLURBS[n]}</small>
            </button>
          ))}
        </div>
        {gatesKnown ? (
          <BotGateChips gates={chips} handlers={handlers} />
        ) : (
          <p className="bots-hero__stale" role="status" data-testid="bots-gates-unreported">{BOTS_STALE_API}</p>
        )}
      </div>

      <div className="bots-hero__actions">
        {armed ? (
          <button type="button" className="bots-btn bots-btn--block" data-testid="bots-stop" disabled={busy}
            data-why={busy ? BOTS_BUSY_WHY : undefined} onClick={() => void stop()}>
            ■ {BOT_DEACTIVATE_LABEL}
          </button>
        ) : (
          <button
            type="button"
            className="bots-btn bots-btn--primary bots-btn--block"
            data-testid="bots-activate"
            disabled={busy || activateBlocked}
            data-why={busy ? BOTS_BUSY_WHY : activateBlocked && activateReason ? prose(activateReason) : undefined}
            onClick={() => { if (!activateBlocked) void activate(); }}
          >
            ▶ {BOT_ACTIVATE_LABEL} bot
          </button>
        )}
        {!armed && level >= 2 && waitsOn.length > 0 ? (
          <p className="bots-hero__hint" data-testid="bots-activate-hint">
            {BOTS_ACTIVATE_WAITS_ON}: {waitsOn.join(', ').toLowerCase()}
          </p>
        ) : null}
        {level >= 2 ? (
          <label className="bots-switch" data-testid="bots-in-control-label">
            <input
              type="checkbox"
              role="switch"
              data-testid="bots-in-control"
              checked={armed}
              aria-checked={armed}
              disabled={busy || (!armed && activateBlocked)}
              data-why={busy ? BOTS_BUSY_WHY : !armed && activateBlocked && activateReason ? prose(activateReason) : undefined}
              onChange={e => void onControl(e.target.checked)}
            />
            <span className="bots-switch__track" aria-hidden="true" />
            <span>{BOTS_IN_CONTROL_LABEL}</span>
          </label>
        ) : null}
        {tripped ? (
          <>
            <p className="bots-hero__killed" role="status">{BOTS_KILL_TRIPPED_NOTE}</p>
            <button type="button" className="bots-btn bots-btn--block" data-testid="bots-kill-reset"
              disabled={killSwitch.busy} data-why={killSwitch.busy ? BOTS_KILL_BUSY_WHY : undefined}
              onClick={() => void killSwitch.act(false)}>
              {BOTS_KILL_RESET_LABEL}
            </button>
          </>
        ) : (
          <button type="button" className="bots-btn bots-btn--danger bots-btn--block" data-testid="bots-kill-trip"
            disabled={killSwitch.busy || killSwitch.status == null}
            data-why={killSwitch.busy ? BOTS_KILL_BUSY_WHY
              : killSwitch.status == null ? BOTS_KILL_UNREAD_WHY(killSwitch.error ?? null) : undefined}
            onClick={() => void killSwitch.act(true)}>
            ■ {BOTS_KILL_TRIP_LABEL} <small>{BOTS_KILL_TRIP_NOTE}</small>
          </button>
        )}
        {killSwitch.error ? <p className="bots-hero__error" data-testid="bots-kill-error">{killSwitch.error}</p> : null}
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
