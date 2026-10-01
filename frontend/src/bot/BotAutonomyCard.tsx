/**
 * The bot as a quiet right-rail card in the Trader (approved redesign, 2026-09-21; ADR
 * 042): the master level -- the most any setup may do on this venue -- how many setups
 * are at Strategy (their names on hover), the bot's stocks, and Active / Not active with
 * the reason, next to Activate / Deactivate. Same session, same rules, same Activate as
 * the Bots page hero (`useBotArm`): choosing a level never activates the bot, Activate
 * is locked with the reason until the backend would accept it, and after a bot trip it
 * asks first.
 */
import { useState } from 'react';
import { writeNovaApiKey } from '../api/novaFetch';
import {
  BOT_ACTIVATE_LABEL,
  BOT_API_KEY_HINT,
  BOT_API_KEY_SAVE,
  BOT_DEACTIVATE_LABEL,
  BOT_LEVEL_FIELD_LABEL,
  BOT_LEVEL_HINTS,
  BOT_LEVEL_LABELS,
} from '../constantGroups/bot';
import { BOTS_BUSY_WHY, BOTS_KEY_EMPTY_WHY, BOTS_REENABLE_OK, BOTS_SESSION_LOADING_WHY, botsAtStrategy } from '../constantGroups/bots_page';
import { BOT_CARD_TITLE } from '../constantGroups/trader_chrome';
import { tipProps } from '../ux/hoverTip';
import { BotArmAllowlistControl } from './BotArmAllowlistControl';
import { botHeaderState } from './botHeaderState';
import { setupNames, strategySetups } from './botLevels';
import { prose } from './botsPageFormat';
import { useBotArm } from './useBotArm';
import './botAutonomyCard.css';

export function BotAutonomyCard() {
  const { session, error, busy, stop, active, level, lock, showKeyField, onLevel, onActivate } = useBotArm();
  const [keyDraft, setKeyDraft] = useState('');
  const view = session ? botHeaderState(session) : null;
  const at = strategySetups(session);
  const activateWhy = busy ? BOTS_BUSY_WHY : lock.why;
  const stateText = !view ? '' : view.state || view.name;

  return (
    <section
      className={`bot-card${view?.tone === 'on' ? ' bot-card--trading' : ''}${active ? ' bot-card--armed' : ''}`}
      data-testid="bot-autonomy-card"
      aria-label={BOT_CARD_TITLE}
    >
      <div className="bot-card__row">
        <span className="bot-card__title">{BOT_CARD_TITLE}</span>
        <span
          className={`bot-card__state${view?.tone === 'on' ? ' bot-card__state--active' : ''}`}
          data-testid="bot-card-state"
          {...tipProps(view?.title ?? null, BOT_CARD_TITLE)}
        >
          {stateText}
        </span>
        {active ? (
          <button type="button" className="bot-card__act" data-testid="bot-card-stop" disabled={busy || !session}
            data-why={busy ? BOTS_BUSY_WHY : !session ? BOTS_SESSION_LOADING_WHY : undefined}
            onClick={() => void stop()}>
            {BOT_DEACTIVATE_LABEL}
          </button>
        ) : (
          <button type="button" className="bot-card__act" data-testid="bot-card-activate"
            disabled={activateWhy != null}
            data-why={activateWhy ?? undefined}
            onClick={() => { if (activateWhy == null) void onActivate(); }}>
            {lock.reenable && !lock.why ? BOTS_REENABLE_OK : BOT_ACTIVATE_LABEL}
          </button>
        )}
      </div>
      {view?.reason && level >= 2 ? (
        <p className="bot-card__reason" data-testid="bot-card-reason">{prose(view.reason)}</p>
      ) : null}
      <div className="bot-card__row bot-card__row--pickers">
        <label className="bot-card__kv">
          <span className="bot-card__k">{BOT_LEVEL_FIELD_LABEL}</span>
          <select aria-label={BOT_LEVEL_FIELD_LABEL} data-testid="bot-card-level" value={level}
            disabled={busy || !session} title={busy || !session ? undefined : prose(BOT_LEVEL_HINTS[level])}
            data-why={busy ? BOTS_BUSY_WHY : !session ? BOTS_SESSION_LOADING_WHY : undefined}
            onChange={event => void onLevel(Number(event.target.value))}>
            <option value={0}>{BOT_LEVEL_LABELS[0]}</option>
            <option value={1}>{BOT_LEVEL_LABELS[1]}</option>
            <option value={2}>{BOT_LEVEL_LABELS[2]}</option>
          </select>
        </label>
        <span className="bot-card__kv bot-card__kv--setup" data-testid="bot-card-at-strategy"
          {...tipProps(`At Strategy: ${setupNames(at)}. Set each setup's own level on the Bots page.`, botsAtStrategy(at.length))}>
          <span className="bot-card__v">{botsAtStrategy(at.length)}</span>
        </span>
        <BotArmAllowlistControl />
      </div>
      {error ? <p className="bot-card__error" data-testid="bot-card-error" role="alert">{prose(error)}</p> : null}
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
