/**
 * A bot family's key at the top of its page (operator decisions 2026-10-15): Strategy Bots or LiveTrader Bots, one
 * per venue. A bot places orders only while the header's Bot switch, this key and its own key are all on; off, its
 * bots place none, not even a sell. Locked on Live with why; a refused press says why under it. `compact` is the
 * switch alone, its words on hover, for the head of LiveTrader Bots (approved render, 2026-10-15).
 */
import { useState } from 'react';
import { DESK_BOT_POLL_MS } from '../constants';
import {
  BOT_FAMILY_NAMES,
  BOT_KEY_LIVE_WHY,
  BOT_KEY_OFF_LINE,
  BOTS_BUSY_WHY,
  botKeyUnreadable,
  BOTS_VENUE_NAMES,
  botKeyOnLine,
  botKeyTip,
} from '../constantGroups/bots_page';
import { tipProps, whyProps } from '../ux';
import { getBotSessionSnapshot } from './botSessionPoller';
import { prose } from './botsPageFormat';
import type { BotFamily } from './types';
import { useBotSession } from './useBotSession';
import './botFamilyKey.css';

export function BotFamilyKey({ family, compact = false }: { family: BotFamily; compact?: boolean }) {
  const { session, busy, setKey } = useBotSession(DESK_BOT_POLL_MS);
  const [refused, setRefused] = useState<string | null>(null);
  const keys = session?.keys;
  if (!keys) return null;                       // the sample desk, or an older backend: no family keys
  const name = BOT_FAMILY_NAMES[family];
  const row = keys[family];
  if (!row || typeof row.on !== 'boolean') {
    // A partial or skewed answer is said, never drawn as on or off (Codex review, PR #1006).
    return compact ? (
      <span className="bot-key bot-key--compact" data-testid={`bot-key-${family}`}>
        <span className="bot-key__error" role="alert">{botKeyUnreadable(name)}</span>
      </span>
    ) : (
      <section className="bot-key" data-testid={`bot-key-${family}`}>
        <p className="bot-key__error" role="alert">{botKeyUnreadable(name)}</p>
      </section>
    );
  }
  const on = row.on;
  const lock = busy ? BOTS_BUSY_WHY : keys.venue === 'live' ? BOT_KEY_LIVE_WHY : keys.error ? prose(keys.error) : null;
  const venue = keys.venue ? BOTS_VENUE_NAMES[keys.venue] ?? keys.venue : '?';

  async function press() {
    setRefused(null);
    const next = await setKey(family, !on);
    if (!next) setRefused(getBotSessionSnapshot().error ?? 'the key did not change');
  }

  const line = keys.venue === 'live' ? BOT_KEY_LIVE_WHY : on ? botKeyOnLine(name, venue) : BOT_KEY_OFF_LINE;
  const switchButton = (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={`${name} key`}
      className="bot-key__switch"
      disabled={lock !== null}
      {...(lock ? whyProps(true, lock) : tipProps(compact ? `${line}\n${botKeyTip(name)}` : botKeyTip(name), `${name} key`))}
      onClick={() => void press()}
      data-testid={`bot-key-${family}-switch`}
    >
      <span className="bot-key__track" aria-hidden="true" />
    </button>
  );

  if (compact) {
    return (
      <span className={`bot-key bot-key--compact${on ? ' is-on' : ''}`} data-testid={`bot-key-${family}`}>
        {switchButton}
        <span className="bot-key__label">Key</span>
        <span className={`bot-key__state${on ? ' is-on' : ''}`} data-testid={`bot-key-${family}-line`} {...tipProps(line, `${name} key`)}>
          {on ? 'ON' : 'OFF'}
        </span>
        {refused ? <span className="bot-key__error" role="alert" data-testid={`bot-key-${family}-error`}>{prose(refused)}</span> : null}
      </span>
    );
  }

  return (
    <section className={`bot-key${on ? ' is-on' : ''}`} data-testid={`bot-key-${family}`}>
      {switchButton}
      <div className="bot-key__txt">
        <b>{name}</b>
        <small data-testid={`bot-key-${family}-line`}>{line}</small>
      </div>
      <span className={`bot-key__state${on ? ' is-on' : ''}`}>{on ? 'ON' : 'OFF'}</span>
      {refused ? <p className="bot-key__error" role="alert" data-testid={`bot-key-${family}-error`}>{prose(refused)}</p> : null}
    </section>
  );
}
