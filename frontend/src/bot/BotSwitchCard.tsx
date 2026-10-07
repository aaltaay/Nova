/**
 * The Bot card (ADR 044): the one Bot switch for this venue, Freeze all orders, and what the bot may risk.
 * One bot for both sides (ADR 049, #778 step 5): each strategy at On trades its own side, and the trade line
 * names it (▲ long or ▼ short).
 * The switch replaces the master dial and Activate: on is the master at Strategy with Activate, off leaves
 * the master at Eyes so alerts keep coming. After the bot trip it asks first, in words, before it turns
 * on again. On Live it is locked and says why. Nothing here places an order.
 */
import { useState, type ReactNode } from 'react';
import { writeNovaApiKey } from '../api/novaFetch';
import { BOT_API_KEY_HINT, BOT_API_KEY_SAVE } from '../constantGroups/bot';
import { BOTS_KEY_EMPTY_WHY } from '../constantGroups/bots_page';
import { tipProps, whyProps } from '../ux';
import { BotKillSwitch } from './BotKillSwitch';
import { botHeaderState } from './botHeaderState';
import { nextTradeLine, prose, sessionVenueName, tradeLine } from './botsPageFormat';
import { offWords } from './botSwitch';
import type { BotArm } from './useBotArm';
import type { KillSwitchControl } from './useKillSwitch';

export const BOT_CARD_ANCHOR = 'bots-bot-card';

const ON_TIP = 'On: the bot may act on the GO triggers of strategies at On, on the stocks whose Entry is Bot -- '
  + 'a long strategy buys, a short strategy shorts. Click to turn it off; Eyes keep running.';
const OFF_TIP = 'Off: the bot trades nothing by itself. Strategies at Eyes or On still alert you. Click to turn it on.';
/** The one-bot words under the switch (#778 step 5). */
const BOTH_SIDES = 'One bot for both sides: each strategy at On trades its own side.';

/** A write the backend refused for want of the desk's API key: save it here (it stays in this desk). */
export function ApiKeyField({ className = 'bots-hero__key', testId = 'bots-api-key' }: { className?: string; testId?: string }) {
  const [draft, setDraft] = useState('');
  return (
    <form className={className} data-testid={testId}
      onSubmit={e => { e.preventDefault(); writeNovaApiKey(draft); setDraft(''); }}>
      <input type="password" autoComplete="off" value={draft} aria-label={BOT_API_KEY_HINT}
        placeholder={BOT_API_KEY_HINT} onChange={e => setDraft(e.target.value)} />
      <button type="submit" className="bots-btn" disabled={!draft.trim()}
        {...whyProps(!draft.trim(), BOTS_KEY_EMPTY_WHY)}>{BOT_API_KEY_SAVE}</button>
    </form>
  );
}

export function BotSwitchCard({ arm, killSwitch, breakers, children }: {
  arm: BotArm;
  killSwitch: KillSwitchControl;
  /** The loss breakers: what turns the Bot off (the bot trip) and locks every buy (the all-stop). */
  breakers?: ReactNode;
  children: ReactNode;
}) {
  const { session, error, on, lock, onSwitch, showKeyField } = arm;
  if (!session) return null;
  const notReady = on ? botHeaderState(session).reason : null;
  const trade = tradeLine(session.trade);
  const next = nextTradeLine(session, on);
  return (
    <section className="bots-card bots-botcard" id={BOT_CARD_ANCHOR} data-testid="bots-bot-card">
      <div className="bots-botcard__left">
        <h3 className="bots-botcard__title">Bot</h3>
        <button
          type="button"
          className={`bots-switch${on ? ' is-on' : ''}`}
          role="switch"
          aria-checked={on}
          disabled={lock !== null}
          {...(lock ? whyProps(true, lock) : tipProps(on ? ON_TIP : OFF_TIP, 'Bot'))}
          onClick={() => void onSwitch(!on)}
          data-testid="bots-switch"
        >
          <span className="bots-switch__track" aria-hidden="true" />
          <span className="bots-switch__txt">
            <b>Bot is {on ? 'on' : 'off'}</b>
            <small data-testid="bots-switch-why">{on ? `On for ${sessionVenueName(session)}. ${BOTH_SIDES}${notReady ? ` ${notReady}.` : ''}` : offWords(session)}</small>
          </span>
          <span className={`bots-switch__state${on ? ' is-on' : ''}`}>{on ? 'ON' : 'OFF'}</span>
        </button>
        {trade ? <p className="bots-botcard__trade" data-testid="bots-trade">{trade}</p> : null}
        {next ? <p className="bots-botcard__trade bots-botcard__next" data-testid="bots-next-trade">{next}</p> : null}
        <p className="bots-botcard__note">The same switch on Paper, Sim and Live. On Live the bot does not trade yet: your PIN unlocks your own orders. Its way to Live is #606, then your 1-share test.</p>
        <p className="bots-botcard__note">Off or on, the radars, the Eyes alerts and the chart's setups and levels keep running.</p>
        {breakers ? <div className="bots-botcard__breakers" data-testid="bots-breakers">{breakers}</div> : null}
        <div className="bots-freeze" data-testid="bots-freeze">
          <BotKillSwitch killSwitch={killSwitch} />
        </div>
        {error ? <p className="bots-hero__error" role="alert" data-testid="bots-error">{prose(error)}</p> : null}
        {showKeyField ? <ApiKeyField /> : null}
      </div>
      <div className="bots-botcard__right">{children}</div>
    </section>
  );
}
