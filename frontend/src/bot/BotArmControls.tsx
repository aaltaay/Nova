import { useState } from 'react';
import { writeNovaApiKey } from '../api/novaFetch';
import {
  BOT_ACTIVATE_LABEL,
  BOT_API_KEY_HINT,
  BOT_API_KEY_SAVE,
  BOT_AUTONOMY_LABEL,
  BOT_DEACTIVATE_LABEL,
  BOT_IN_CONTROL_LABEL,
  BOT_LEVEL_FIELD_LABEL,
  BOT_LEVEL_HINTS,
  BOT_LEVEL_LABELS,
  BOT_PACK_FIELD_LABEL,
  BOT_PACK_LABELS,
  BOT_PACKS,
  BOT_STATE_ACTIVE,
  BOT_STATE_NOT_ACTIVE,
  packDescription,
  packStatus,
} from '../constantGroups/bot';
import { DESK_BOT_POLL_MS } from '../constants';
import { BotArmAllowlistControl } from './BotArmAllowlistControl';
import { useBotSession } from './useBotSession';

export function BotArmControls() {
  const { session, error, busy, patch, activate, stop } = useBotSession(DESK_BOT_POLL_MS);
  const [pickedPack, setPickedPack] = useState<string | null>(null);
  const [keyDraft, setKeyDraft] = useState('');
  const level = session?.level ?? 0;
  const armed = Boolean(session?.armed);
  const live = Boolean(session?.live_fire_ready);
  const sessionPack = String(session?.active_pack || 'halt-luld');
  const pack = pickedPack ?? sessionPack;
  const packs = session?.packs?.length
    ? session.packs
    : BOT_PACKS.map(id => ({
        id,
        label: BOT_PACK_LABELS[id],
        status: packStatus(id),
        description: packDescription(id),
      }));
  const selected = packs.find(row => row.id === pack);
  const description = selected?.description || packDescription(pack);
  const showControlBox = level >= 2;
  const idle = !armed && !live;
  const stateLabel = armed ? BOT_STATE_ACTIVE : BOT_STATE_NOT_ACTIVE;
  const showKeyField = Boolean(error && /api key/i.test(error));

  async function onLevel(next: number) {
    if (next >= 2 && !armed) {
      const armedSession = await activate();
      if (!armedSession) return;
    }
    await patch({ level: next });
  }

  async function onControl(next: boolean) {
    if (level < 2) return;
    if (next) await activate();
    else await stop();
  }

  function onSaveKey() {
    writeNovaApiKey(keyDraft);
    setKeyDraft('');
  }

  return (
    <div
      className={`bot-arm${live ? ' bot-arm--live' : ''}${armed ? ' bot-arm--armed' : ''}${idle ? ' bot-arm--idle' : ''}`}
      data-testid="bot-arm-controls"
    >
      <span className="bot-arm__name" data-testid="bot-arm-name">{BOT_AUTONOMY_LABEL}</span>
      <label className="bot-arm__field">
        <span className="bot-arm__label">{BOT_LEVEL_FIELD_LABEL}</span>
        <select
          aria-label={BOT_LEVEL_FIELD_LABEL}
          data-testid="bot-arm-level"
          value={level > 2 ? 2 : level}
          disabled={busy || !session}
          title={BOT_LEVEL_HINTS[(level > 2 ? 2 : level) as 0 | 1 | 2]}
          onChange={event => void onLevel(Number(event.target.value))}
        >
          <option value={0} title={BOT_LEVEL_HINTS[0]}>{BOT_LEVEL_LABELS[0]}</option>
          <option value={1} title={BOT_LEVEL_HINTS[1]}>{BOT_LEVEL_LABELS[1]}</option>
          <option value={2} title={BOT_LEVEL_HINTS[2]}>{BOT_LEVEL_LABELS[2]}</option>
        </select>
      </label>
      <div className="bot-arm__pack">
        <div className="bot-arm__pack-tools">
          <label className="bot-arm__field">
            <span className="bot-arm__label">{BOT_PACK_FIELD_LABEL}</span>
            <select
              aria-label={BOT_PACK_FIELD_LABEL}
              aria-describedby={description ? 'bot-arm-pack-desc' : undefined}
              data-testid="bot-arm-pack"
              value={pack}
              disabled={busy || !session}
              title={description}
              onChange={event => {
                const next = event.target.value;
                setPickedPack(next);
                void patch({ active_pack: next });
              }}
            >
              {packs.map(row => (
                <option key={row.id} value={row.id}>
                  {row.label}
                </option>
              ))}
            </select>
          </label>
          <BotArmAllowlistControl />
        </div>
        {description ? (
          <p
            id="bot-arm-pack-desc"
            className="bot-arm__desc"
            data-testid="bot-arm-pack-desc"
            title={description}
          >
            {description}
          </p>
        ) : null}
      </div>
      <span
        className={`bot-arm__status${armed ? ' bot-arm__status--active' : ' bot-arm__status--idle'}`}
        data-testid="bot-arm-status"
      >
        {stateLabel}
      </span>
      {armed ? (
        <button
          type="button"
          className="bot-arm__btn"
          data-testid="bot-arm-stop"
          disabled={busy || !session}
          onClick={() => void stop()}
        >
          {BOT_DEACTIVATE_LABEL}
        </button>
      ) : (
        <button
          type="button"
          className="bot-arm__btn"
          data-testid="bot-arm-activate"
          disabled={busy}
          onClick={() => void activate()}
        >
          {BOT_ACTIVATE_LABEL}
        </button>
      )}
      {showControlBox ? (
        <label className="bot-arm__check" data-testid="bot-arm-in-control-label">
          <input
            type="checkbox"
            data-testid="bot-arm-in-control"
            checked={armed}
            disabled={busy || !session}
            onChange={event => void onControl(event.target.checked)}
          />
          {BOT_IN_CONTROL_LABEL}
        </label>
      ) : null}
      {error ? (
        <p className="bot-arm__error" data-testid="bot-arm-error" role="alert">
          {error}
        </p>
      ) : null}
      {showKeyField ? (
        <form
          className="bot-arm__key"
          data-testid="bot-arm-api-key"
          onSubmit={event => {
            event.preventDefault();
            onSaveKey();
          }}
        >
          <label className="bot-arm__field">
            <span className="bot-arm__label">{BOT_API_KEY_HINT}</span>
            <input
              type="password"
              autoComplete="off"
              value={keyDraft}
              onChange={event => setKeyDraft(event.target.value)}
              aria-label={BOT_API_KEY_HINT}
            />
          </label>
          <button type="submit" className="bot-arm__btn" disabled={!keyDraft.trim()}>
            {BOT_API_KEY_SAVE}
          </button>
        </form>
      ) : null}
    </div>
  );
}
