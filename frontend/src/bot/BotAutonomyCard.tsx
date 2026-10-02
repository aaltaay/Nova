/**
 * The Bot switch as a quiet card at the bottom of the Trader's right rail (ADR 044): the same one switch
 * as the Bots page, for this venue, with why it is off (or not trading now) and how many strategies are
 * On. Same rules as the Bots page (`useBotArm`): off always goes, on is locked with the reason where the
 * bot cannot trade, and after the bot trip it asks first. Who trades this stock is the Who trades row
 * above Level 2; the strategies and the hot list are on the Bots page.
 */
import { BOT_CARD_TITLE } from '../constantGroups/trader_chrome';
import { tipProps, whyProps } from '../ux';
import { setNavPage, useWorkspace } from '../workspace';
import { botHeaderState } from './botHeaderState';
import { prose } from './botsPageFormat';
import { ApiKeyField } from './BotSwitchCard';
import { useBotArm } from './useBotArm';
import './botAutonomyCard.css';

export function BotAutonomyCard() {
  const { session, error, on, lock, onSwitch, showKeyField } = useBotArm();
  const { traderViewActive, showScannerView } = useWorkspace();
  const view = session ? botHeaderState(session) : null;
  const openBots = () => {
    if (traderViewActive) showScannerView();
    setNavPage('bots');
  };
  return (
    <section
      className={`bot-card${view?.tone === 'on' ? ' bot-card--trading' : ''}${on ? ' bot-card--armed' : ''}`}
      data-testid="bot-autonomy-card"
      aria-label={BOT_CARD_TITLE}
    >
      <div className="bot-card__row">
        <span className="bot-card__title">{BOT_CARD_TITLE}</span>
        <span className={`bot-card__state${on ? ' bot-card__state--active' : ''}`} data-testid="bot-card-state"
          {...tipProps(view?.title ?? null, BOT_CARD_TITLE)}>
          {view ? (on ? `ON · ${view.detail}` : 'OFF') : ''}
        </span>
        <button type="button" className={`bot-card__switch${on ? ' is-on' : ''}`} role="switch" aria-checked={on}
          aria-label="Bot" disabled={lock !== null} {...whyProps(lock !== null, lock)}
          onClick={() => void onSwitch(!on)} data-testid="bot-card-switch">
          <span className="bot-card__track" aria-hidden="true" />
        </button>
      </div>
      {view?.reason ? <p className="bot-card__reason" data-testid="bot-card-reason">{prose(view.reason)}</p> : null}
      <button type="button" className="bot-card__link" data-testid="bot-card-open" onClick={openBots}>
        Strategies, hot list and every gate: Bots page ↗
      </button>
      {error ? <p className="bot-card__error" data-testid="bot-card-error" role="alert">{prose(error)}</p> : null}
      {showKeyField ? <ApiKeyField className="bot-card__key" testId="bot-card-api-key" /> : null}
    </section>
  );
}
