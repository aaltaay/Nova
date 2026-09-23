/**
 * The Bots page (approved mockup v4, ADR 027): your playbook, run by the bot --
 * what it watches, what it may risk, what it proposed and did. The hero holds
 * the level, every gate and Activate; the strategies card holds the setups
 * from the operator's material; the right column is the proposals inbox, the
 * activity timeline and the scoreboard. Nothing on this page places an order
 * except through the bot's own gated path.
 */
import { BOT_ACTION_KINDS } from '../constantGroups/bot';
import { BotActivity } from './BotActivity';
import { BotHero } from './BotHero';
import { BotProposalsInbox } from './BotProposalsInbox';
import { BotRiskCard } from './BotRiskCard';
import { BotStrategiesCard } from './BotStrategiesCard';
import { BotSymbolsCard } from './BotSymbolsCard';
import { BotTodayCard } from './BotTodayCard';
import { KillSwitchCard } from './KillSwitchCard';
import { useBotSession } from './useBotSession';
import './botsPage.css';

export function StrategyTab() {
  const { session, proposals, audit, error, busy, patch, resolve } = useBotSession();

  if (!session) {
    return <div className="bot-strategy empty-state">{error || 'Loading bot session…'}</div>;
  }

  return (
    <div className="bot-strategy bots-page" data-testid="bots-page">
      {/* The tab host already titles the page "Bots" (QA V30). */}
      <header className="bots-page__head">
        <p className="bots-muted">Your playbook, run by the bot: what it watches, what it may risk, what it proposed and did.</p>
        {busy ? <span className="bots-muted">Saving…</span> : null}
      </header>

      {session.day_lock_active ? (
        <div className="bot-strategy__banner bot-strategy__banner--hard" role="alert">
          -$200 day lock is on. Bot and manual buys stay blocked until midnight
          America/New_York ({session.hard_lock_until_date}). Flatten / kill still work.
        </div>
      ) : null}
      {session.soft_breaker_fired && !session.day_lock_active ? (
        <div className="bot-strategy__banner" role="status">
          -$50 breaker flattened the account and dropped the bot to L0.
          Desk can still trade. Activate re-enables it.
        </div>
      ) : null}

      <BotHero />

      <div className="bots-grid">
        <div className="bots-col">
          <BotStrategiesCard session={session} />
          <div className="bots-row2">
            <BotSymbolsCard session={session} />
            <BotRiskCard session={session} patch={patch} />
          </div>
        </div>
        <div className="bots-col">
          <BotProposalsInbox proposals={proposals} resolve={resolve} />
          <KillSwitchCard />
          <BotActivity audit={audit} />
          <BotTodayCard />
        </div>
      </div>

      <footer className="bots-foot">
        <span>{session.working.length} bot working order{session.working.length === 1 ? '' : 's'}</span>
        <span>Order kinds the bot may send: {BOT_ACTION_KINDS.join(' · ')}. Free-form quantity is refused.</span>
      </footer>
    </div>
  );
}
