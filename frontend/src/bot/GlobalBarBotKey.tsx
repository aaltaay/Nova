/**
 * The Bot switch in the header, beside the padlock (operator decision 2026-10-15): the master key over every bot on
 * this venue, on every view. Off, no bot places an order, not even a sell; under it each bot family has its key at
 * the top of its page (Bots > LiveTrader Bots, Bots > Strategy Bots). The dot says whether it would trade now; hover
 * says why it is off or not trading; a refused press says why under the key. Same rules as every surface that drives
 * the switch (`useBotArm`). The sample desk has no bot: no key.
 */
import { useEffect, useState } from 'react';
import { BOT_HEADER_KEY_TIP, BOTS_PILL_LABEL } from '../constantGroups/bots_page';
import { whyProps } from '../ux';
import { botHeaderState } from './botHeaderState';
import { getBotSessionSnapshot } from './botSessionPoller';
import { prose } from './botsPageFormat';
import { useBotArm } from './useBotArm';
import './globalBarBotKey.css';

/** How long a refusal stays under the key. */
const REFUSED_MS = 8_000;

export function GlobalBarBotKey() {
  const { session, on, lock, onSwitch } = useBotArm();
  const [refused, setRefused] = useState<string | null>(null);
  useEffect(() => {
    if (!refused) return undefined;
    const t = window.setTimeout(() => setRefused(null), REFUSED_MS);
    return () => window.clearTimeout(t);
  }, [refused]);
  if (!session) return null;
  const view = botHeaderState(session);

  async function press() {
    setRefused(null);
    const next = await onSwitch(!on);
    if (!next) setRefused(getBotSessionSnapshot().error ?? 'the Bot switch did not change');
  }

  return (
    <span className="global-bar-bot-key-slot" data-testid="global-bar-bot-key-slot">
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-label="Bot switch"
        className={`global-bar-bot-key global-bar-bot-key--${view.tone}`}
        disabled={lock !== null}
        {...whyProps(lock !== null, lock)}
        title={lock ? undefined : `${view.title} · ${BOT_HEADER_KEY_TIP}`}
        onClick={() => void press()}
        data-testid="global-bar-bot-key"
      >
        <span className="global-bar-bot-key__dot" aria-hidden="true" />
        <span className="global-bar-bot-key__label">{BOTS_PILL_LABEL}</span>
        <span className="global-bar-bot-key__track" aria-hidden="true" />
        <b className="global-bar-bot-key__name" data-testid="global-bar-bot-key-name">{view.name}</b>
      </button>
      {refused ? (
        <span className="global-bar-bot-key__refused" role="alert" data-testid="global-bar-bot-key-refused">
          {prose(refused)}
        </span>
      ) : null}
    </span>
  );
}
