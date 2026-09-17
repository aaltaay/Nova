import { useState } from 'react';
import {
  BOT_IN_CONTROL_LABEL,
  BOT_LEVEL_LABELS,
  BOT_PACK_LABELS,
  BOT_PACKS,
  packDescription,
} from '../constantGroups/bot';
import { DESK_BOT_POLL_MS } from '../constants';
import { useBotSession } from './useBotSession';

export function BotArmControls() {
  const { session, error, busy, patch, activate, stop } = useBotSession(DESK_BOT_POLL_MS);
  const [pickedPack, setPickedPack] = useState<string | null>(null);
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
        status: id === 'halt-luld' || id === 'llm-decide' ? 'live' : 'stub',
        description: packDescription(id),
      }));
  const selected = packs.find(row => row.id === pack);
  const description = selected?.description || packDescription(pack);
  const showControlBox = level >= 2;
  const idle = !armed && !live;

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

  return (
    <div
      className={`bot-arm${live ? ' bot-arm--live' : ''}${armed ? ' bot-arm--armed' : ''}${idle ? ' bot-arm--idle' : ''}`}
      data-testid="bot-arm-controls"
    >
      <label className="bot-arm__field">
        <span className="bot-arm__sr">Bot autonomy</span>
        <select
          aria-label="Bot autonomy"
          data-testid="bot-arm-level"
          value={level > 2 ? 2 : level}
          disabled={busy || !session}
          onChange={event => void onLevel(Number(event.target.value))}
        >
          <option value={0}>{BOT_LEVEL_LABELS[0]}</option>
          <option value={1}>{BOT_LEVEL_LABELS[1]}</option>
          <option value={2}>{BOT_LEVEL_LABELS[2]}</option>
        </select>
      </label>
      <label className="bot-arm__field">
        <span className="bot-arm__sr">Bot pack</span>
        <select
          aria-label="Bot pack"
          data-testid="bot-arm-pack"
          value={pack}
          disabled={busy || !session}
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
      ) : (
        <>
          <button
            type="button"
            className="bot-arm__btn"
            data-testid="bot-arm-activate"
            disabled={busy}
            onClick={() => void activate()}
          >
            Activate
          </button>
          <button
            type="button"
            className="bot-arm__btn"
            data-testid="bot-arm-stop"
            disabled={busy || !armed}
            onClick={() => void stop()}
          >
            Stop
          </button>
        </>
      )}
      <span
        className="bot-arm__status"
        data-testid="bot-arm-status"
        title={error || (live ? 'L2 + Activate + brain heartbeat' : 'Not live-fire ready')}
      >
        {live ? 'L2 live ✓' : armed ? 'Armed' : 'Bot off'}
      </span>
      {description ? (
        <p className="bot-arm__desc" data-testid="bot-arm-pack-desc">
          {description}
        </p>
      ) : null}
    </div>
  );
}
