/**
 * The Bot card (ADR 044): Freeze all orders, the bot's trade, and what the bot may risk. The Bot switch it held is
 * in the header beside the padlock since 2026-10-15 (the master key over every bot); the Strategy Bots key is at the
 * top of this page. One bot for both sides (ADR 049, #778 step 5): each strategy at On trades its own side, and the
 * trade line names it (▲ long or ▼ short). The day's loss is capped by the one daily loss limit in Settings > Loss
 * limits (ADR 056), not here. Nothing here places an order.
 */
import { useState, type ReactNode } from 'react';
import { writeNovaApiKey } from '../api/novaFetch';
import { BOT_API_KEY_HINT, BOT_API_KEY_SAVE } from '../constantGroups/bot';
import { BOTS_KEY_EMPTY_WHY } from '../constantGroups/bots_page';
import { whyProps } from '../ux';
import { BotKillSwitch } from './BotKillSwitch';
import { botHeaderState } from './botHeaderState';
import { nextTradeLine, prose, sessionVenueName, tradeLine } from './botsPageFormat';
import { offWords } from './botSwitch';
import type { BotArm } from './useBotArm';
import type { KillSwitchControl } from './useKillSwitch';

export const BOT_CARD_ANCHOR = 'bots-bot-card';

/** The one-bot words on the card (#778 step 5). */
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

export function BotSwitchCard({ arm, killSwitch, children }: {
  arm: BotArm;
  killSwitch: KillSwitchControl;
  children: ReactNode;
}) {
  const { session, error, on, showKeyField } = arm;
  if (!session) return null;
  const notReady = on ? botHeaderState(session).reason : null;
  const trade = tradeLine(session.trade);
  const next = nextTradeLine(session, on);
  return (
    <section className="bots-card bots-botcard" id={BOT_CARD_ANCHOR} data-testid="bots-bot-card">
      <div className="bots-botcard__left">
        <h3 className="bots-botcard__title">Bot</h3>
        <p className="bots-botcard__trade" data-testid="bots-switch-why">
          {on ? `The Bot switch is on for ${sessionVenueName(session)}. ${BOTH_SIDES}${notReady ? ` ${notReady}.` : ''}`
            : `The Bot switch (in the header, beside the padlock) is off. ${offWords(session)}`}
        </p>
        {trade ? <p className="bots-botcard__trade" data-testid="bots-trade">{trade}</p> : null}
        {next ? <p className="bots-botcard__trade bots-botcard__next" data-testid="bots-next-trade">{next}</p> : null}
        <p className="bots-botcard__note">The bot trades on Paper and Sim. On Live, your PIN unlocks your own orders; the bot never trades Live.</p>
        <p className="bots-botcard__note">Off or on, the radars, the Eyes alerts and the chart's setups and levels keep running.</p>
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
