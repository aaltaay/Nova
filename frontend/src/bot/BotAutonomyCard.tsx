/**
 * Bot Autonomy as a quiet right-rail card (approved redesign, 2026-09-21):
 * Level picker, Pack picker with an `i` tooltip for the pack's long sentence,
 * `Allowlist · N`, and the state next to Activate / Deactivate. Same session,
 * same gate, same arm path as the retired full-width bar (BotArmControls):
 * Level 2 arms first, Activate is refused while the desk gate blocks places,
 * and a PIN lock disarms. Nothing here changes what a bot may do.
 */
import { useEffect, useState } from 'react';
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
  BOT_PACK_FIELD_LABEL,
  BOT_PACK_LABELS,
  BOT_PACKS,
  packDescription,
  packStatus,
} from '../constantGroups/bot';
import { BOT_CARD_PACK_INFO_ARIA, BOT_CARD_TITLE } from '../constantGroups/trader_chrome';
import { DESK_BOT_POLL_MS } from '../constants';
import { botArmDisplayState } from '../ibkr/tradingAllowed';
import { useDeskTradingAllowed } from '../ibkr/useDeskTradingAllowed';
import { BotArmAllowlistControl } from './BotArmAllowlistControl';
import { useBotSession } from './useBotSession';
import './botAutonomyCard.css';

export function BotAutonomyCard() {
  const { session, error, busy, patch, activate, stop } = useBotSession(DESK_BOT_POLL_MS);
  const gate = useDeskTradingAllowed();
  const [pickedPack, setPickedPack] = useState<string | null>(null);
  const [keyDraft, setKeyDraft] = useState('');
  const level = session?.level ?? 0;
  const armed = Boolean(session?.armed);
  const display = botArmDisplayState(armed, gate);
  const live = Boolean(session?.live_fire_ready) && display.looksActive;
  const pack = pickedPack ?? String(session?.active_pack || 'halt-luld');
  const packs = session?.packs?.length
    ? session.packs
    : BOT_PACKS.map(id => ({ id, label: BOT_PACK_LABELS[id], status: packStatus(id), description: packDescription(id) }));
  const description = packs.find(row => row.id === pack)?.description || packDescription(pack);
  const activateBlocked = !gate.allowed;
  const showKeyField = Boolean(error && /api key/i.test(error));
  const clampedLevel = (level > 2 ? 2 : level) as 0 | 1 | 2;

  useEffect(() => {
    if (gate.blockers.includes('pin') && armed) void stop();
  }, [gate.blockers, armed, stop]);

  async function onLevel(next: number) {
    if (next >= 2 && !armed) {
      if (activateBlocked) return;
      if (!(await activate())) return;
    }
    await patch({ level: next });
  }

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
          title={gate.reason ?? undefined}
        >
          {display.label}
        </span>
        {armed ? (
          <button type="button" className="bot-card__act" data-testid="bot-card-stop" disabled={busy || !session}
            onClick={() => void stop()}>
            {BOT_DEACTIVATE_LABEL}
          </button>
        ) : (
          <button type="button" className="bot-card__act" data-testid="bot-card-activate"
            disabled={busy || activateBlocked} title={activateBlocked ? gate.reason ?? undefined : undefined}
            onClick={() => { if (!activateBlocked) void activate(); }}>
            {BOT_ACTIVATE_LABEL}
          </button>
        )}
      </div>
      <div className="bot-card__row bot-card__row--pickers">
        <label className="bot-card__kv">
          <span className="bot-card__k">{BOT_LEVEL_FIELD_LABEL}</span>
          <select aria-label={BOT_LEVEL_FIELD_LABEL} data-testid="bot-card-level" value={clampedLevel}
            disabled={busy || !session} title={BOT_LEVEL_HINTS[clampedLevel]}
            onChange={event => void onLevel(Number(event.target.value))}>
            <option value={0}>{BOT_LEVEL_LABELS[0]}</option>
            <option value={1}>{BOT_LEVEL_LABELS[1]}</option>
            <option value={2}>{BOT_LEVEL_LABELS[2]}</option>
          </select>
        </label>
        <label className="bot-card__kv bot-card__kv--pack">
          <span className="bot-card__k">{BOT_PACK_FIELD_LABEL}</span>
          <select aria-label={BOT_PACK_FIELD_LABEL} data-testid="bot-card-pack" value={pack}
            disabled={busy || !session}
            onChange={event => { const next = event.target.value; setPickedPack(next); void patch({ active_pack: next }); }}>
            {packs.map(row => <option key={row.id} value={row.id}>{row.label}</option>)}
          </select>
          {description ? (
            <span className="bot-card__info" role="img" tabIndex={0} aria-label={`${BOT_CARD_PACK_INFO_ARIA}: ${description}`}
              title={description} data-testid="bot-card-pack-info">
              <Info size={13} aria-hidden="true" />
            </span>
          ) : null}
        </label>
        <BotArmAllowlistControl />
      </div>
      {error ? <p className="bot-card__error" data-testid="bot-card-error" role="alert">{error}</p> : null}
      {showKeyField ? (
        <form className="bot-card__key" data-testid="bot-card-api-key"
          onSubmit={event => { event.preventDefault(); writeNovaApiKey(keyDraft); setKeyDraft(''); }}>
          <input type="password" autoComplete="off" value={keyDraft} aria-label={BOT_API_KEY_HINT}
            placeholder={BOT_API_KEY_HINT} onChange={event => setKeyDraft(event.target.value)} />
          <button type="submit" className="bot-card__act" disabled={!keyDraft.trim()}>{BOT_API_KEY_SAVE}</button>
        </form>
      ) : null}
    </section>
  );
}
