/**
 * Bot Autonomy as a quiet right-rail card (approved redesign, 2026-09-21):
 * Level picker, the setup that plays with an `i` tooltip for what it trades
 * (ADR 027), `Allowlist · N`, and the state next to Activate / Deactivate.
 * Same session, same gate, same arm path as the Bots page hero (`useBotArm`):
 * Level 2 arms first, Activate is refused while the desk gate blocks places
 * or the read-out has not passed, and a PIN lock disarms.
 */
import { useState } from 'react';
import { Info } from 'lucide-react';
import { writeNovaApiKey } from '../api/novaFetch';
import {
  BOT_ACTIVATE_LABEL,
  BOT_API_KEY_HINT,
  BOT_API_KEY_SAVE,
  BOT_DEACTIVATE_LABEL,
  BOT_LEVEL_FIELD_LABEL,
  BOT_LEVEL_HINTS,
  BOT_LEVEL_LABELS,
  BOT_SETUP_BLURBS,
  BOT_SETUP_FIELD_LABEL,
  BOT_SETUP_FIRST_PULLBACK,
  BOT_SETUP_LABELS,
} from '../constantGroups/bot';
import { BOTS_BUSY_WHY, BOTS_KEY_EMPTY_WHY, BOTS_SESSION_LOADING_WHY } from '../constantGroups/bots_page';
import { BOT_CARD_SETUP_INFO_ARIA, BOT_CARD_TITLE } from '../constantGroups/trader_chrome';
import { BotArmAllowlistControl } from './BotArmAllowlistControl';
import { useBotArm } from './useBotArm';
import './botAutonomyCard.css';

export function BotAutonomyCard() {
  const {
    session, error, busy, stop, activate, armed, level, display, live,
    activateBlocked, activateReason, showKeyField, onLevel,
  } = useBotArm();
  const [keyDraft, setKeyDraft] = useState('');
  const setup = session?.setup || BOT_SETUP_FIRST_PULLBACK;
  const description = BOT_SETUP_BLURBS[setup] ?? '';
  const clampedLevel = (level > 2 ? 2 : level) as 0 | 1 | 2;

  return (
    <section
      className={`bot-card${live ? ' bot-card--live' : ''}${display.looksActive ? ' bot-card--armed' : ''}`}
      data-testid="bot-autonomy-card"
      aria-label={BOT_CARD_TITLE}
    >
      <div className="bot-card__row">
        <span className="bot-card__title">{BOT_CARD_TITLE}</span>
        <span
          className={`bot-card__state${display.looksActive ? ' bot-card__state--active' : ''}`}
          data-testid="bot-card-state"
          title={activateReason ?? undefined}
        >
          {display.label}
        </span>
        {armed ? (
          <button type="button" className="bot-card__act" data-testid="bot-card-stop" disabled={busy || !session}
            data-why={busy ? BOTS_BUSY_WHY : !session ? BOTS_SESSION_LOADING_WHY : undefined}
            onClick={() => void stop()}>
            {BOT_DEACTIVATE_LABEL}
          </button>
        ) : (
          <button type="button" className="bot-card__act" data-testid="bot-card-activate"
            disabled={busy || activateBlocked}
            data-why={busy ? BOTS_BUSY_WHY : activateBlocked ? activateReason ?? undefined : undefined}
            onClick={() => { if (!activateBlocked) void activate(); }}>
            {BOT_ACTIVATE_LABEL}
          </button>
        )}
      </div>
      <div className="bot-card__row bot-card__row--pickers">
        <label className="bot-card__kv">
          <span className="bot-card__k">{BOT_LEVEL_FIELD_LABEL}</span>
          <select aria-label={BOT_LEVEL_FIELD_LABEL} data-testid="bot-card-level" value={clampedLevel}
            disabled={busy || !session} title={busy || !session ? undefined : BOT_LEVEL_HINTS[clampedLevel]}
            data-why={busy ? BOTS_BUSY_WHY : !session ? BOTS_SESSION_LOADING_WHY : undefined}
            onChange={event => void onLevel(Number(event.target.value))}>
            <option value={0}>{BOT_LEVEL_LABELS[0]}</option>
            <option value={1}>{BOT_LEVEL_LABELS[1]}</option>
            <option value={2}>{BOT_LEVEL_LABELS[2]}</option>
          </select>
        </label>
        <span className="bot-card__kv bot-card__kv--setup">
          <span className="bot-card__k">{BOT_SETUP_FIELD_LABEL}</span>
          <span className="bot-card__v" data-testid="bot-card-setup">{BOT_SETUP_LABELS[setup] ?? setup}</span>
          {description ? (
            <span className="bot-card__info" role="img" tabIndex={0} aria-label={`${BOT_CARD_SETUP_INFO_ARIA}: ${description}`}
              title={description} data-testid="bot-card-setup-info">
              <Info size={13} aria-hidden="true" />
            </span>
          ) : null}
        </span>
        <BotArmAllowlistControl />
      </div>
      {error ? <p className="bot-card__error" data-testid="bot-card-error" role="alert">{error}</p> : null}
      {showKeyField ? (
        <form className="bot-card__key" data-testid="bot-card-api-key"
          onSubmit={event => { event.preventDefault(); writeNovaApiKey(keyDraft); setKeyDraft(''); }}>
          <input type="password" autoComplete="off" value={keyDraft} aria-label={BOT_API_KEY_HINT}
            placeholder={BOT_API_KEY_HINT} onChange={event => setKeyDraft(event.target.value)} />
          <button type="submit" className="bot-card__act" disabled={!keyDraft.trim()}
            data-why={keyDraft.trim() ? undefined : BOTS_KEY_EMPTY_WHY}>{BOT_API_KEY_SAVE}</button>
        </form>
      ) : null}
    </section>
  );
}
