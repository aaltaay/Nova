import { BOT_LEVEL_LABELS, BOT_PACK_LABELS, BOT_PACKS } from '../constantGroups/bot';
import { useBotSession } from './useBotSession';

export function BotArmControls() {
  const { session, error, busy, patch, activate, stop } = useBotSession(2500);
  const level = session?.level ?? 0;
  const armed = Boolean(session?.armed);
  const live = Boolean(session?.live_fire_ready);
  const pack = String(session?.active_pack || 'halt-luld');
  const packs = session?.packs?.length
    ? session.packs
    : BOT_PACKS.map(id => ({
        id,
        label: BOT_PACK_LABELS[id],
        status: id === 'halt-luld' ? 'live' : 'stub',
      }));

  async function onLevel(next: number) {
    if (next >= 2 && !armed) {
      const armedSession = await activate();
      if (!armedSession) return;
    }
    await patch({ level: next });
  }

  return (
    <div
      className={`bot-arm${live ? ' bot-arm--live' : ''}${armed ? ' bot-arm--armed' : ''}`}
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
          onChange={event => void patch({ active_pack: event.target.value })}
        >
          {packs.map(row => (
            <option key={row.id} value={row.id}>
              {row.label}
            </option>
          ))}
        </select>
      </label>
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
      <span
        className="bot-arm__status"
        data-testid="bot-arm-status"
        title={error || (live ? 'L2 + Activate + brain heartbeat' : 'Not live-fire ready')}
      >
        {live ? 'L2 live ✓' : armed ? 'Armed' : 'Bot off'}
      </span>
    </div>
  );
}
