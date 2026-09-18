import { BOT_ACTION_KINDS, BOT_PACK_LABELS, packDescription, quoteSpikeSettingsLine } from '../constantGroups/bot';
import { useBotSession } from './useBotSession';

export function StrategyTab() {
  const { session, proposals, audit, error, busy, patch, resolve } = useBotSession();

  if (!session) {
    return <div className="bot-strategy empty-state">{error || 'Loading bot session…'}</div>;
  }

  const pending = proposals.filter(p => p.status === 'pending');
  const pack = String(session.active_pack || 'halt-luld');
  const packLabel = BOT_PACK_LABELS[pack as keyof typeof BOT_PACK_LABELS] || pack;
  const selectedPack = session.packs?.find(row => row.id === pack);
  const description = selectedPack?.description || packDescription(pack);
  const llm = session.llm ?? {
    configured: false,
    live_fire: false,
    call_cap: 10,
    usd_cap: 2,
    usd_spent: 0,
    calls_used: 0,
  };

  return (
    <div className="bot-strategy">
      <header className="bot-strategy__header">
        <div>
          <h2>Strategy -- small-cap settings</h2>
          <p className="form-hint">
            Autonomy, Activate, and pack live on the header. This tab is risk
            sleeve, Advise, proposals, and audit only. Brains cannot raise L2.
          </p>
        </div>
        {busy ? <span className="form-hint">Saving…</span> : null}
      </header>

      {error ? <div className="empty-state">{error}</div> : null}

      {session.day_lock_active ? (
        <div className="bot-strategy__banner bot-strategy__banner--hard" role="alert">
          -$200 day lock is on. Bot and manual buys stay blocked until midnight
          America/New_York ({session.hard_lock_until_date}). Flatten / kill still work.
        </div>
      ) : null}

      {session.soft_breaker_fired && !session.day_lock_active ? (
        <div className="bot-strategy__banner" role="status">
          -$50 breaker flattened the account and dropped the bot to L0.
          Desk can still trade. Re-arm from the header Activate control.
        </div>
      ) : null}

      <section className="bot-strategy__card">
        <h3>Status (read-only)</h3>
        <p className="form-hint">
          Level {session.level} · {session.armed ? 'Active' : 'Not active'} · pack {packLabel}
          {session.live_fire_ready ? ' · live-fire ready' : ''}
        </p>
        <p className="form-hint">
          Brain: {session.brain_session_id || 'none'}
          {session.brain_alive ? ' (heartbeat alive)' : ' (heartbeat stale or missing)'}
        </p>
        <p className="form-hint">
          Symbol allowlist: {session.symbol_allowlist?.join(', ') || 'empty -- fail closed'}
        </p>
      </section>

      <section className="bot-strategy__card">
        <h3>Small-cap filters</h3>
        <div className="bot-strategy__grid">
          <label>
            Max shares (1-10)
            <input
              type="number"
              min={1}
              max={10}
              value={session.caps.max_shares}
              onChange={e => void patch({ caps: { max_shares: Number(e.target.value) } })}
            />
          </label>
          <label>
            BP budget $ (hard max 50)
            <input
              type="number"
              min={0.01}
              max={50}
              step={0.5}
              value={session.caps.bp_budget_usd}
              onChange={e => void patch({ caps: { bp_budget_usd: Number(e.target.value) } })}
            />
          </label>
          <label>
            Working TTL seconds (1-10)
            <input
              type="number"
              min={1}
              max={10}
              value={session.caps.working_ttl_sec}
              onChange={e => void patch({ caps: { working_ttl_sec: Number(e.target.value) } })}
            />
          </label>
          <label className="bot-strategy__check">
            <input
              type="checkbox"
              checked={session.caps.extended_hours}
              onChange={e => void patch({ caps: { extended_hours: e.target.checked } })}
            />
            Extended hours (off unless you enable it)
          </label>
        </div>
        <p className="form-hint">
          Action kinds: {BOT_ACTION_KINDS.join(', ')}. Free-form qty is refused.
          New buys block while a bot working order exists.
        </p>
        <p className="form-hint">
          Live L2 (max 3, shared with Trader): {session.trader_live.join(', ') || 'none'}
        </p>
        <p className="form-hint" data-testid="bot-pack-desc">
          {description}
        </p>
        {pack === 'quote-spike' ? (
          <p className="form-hint" data-testid="bot-quote-spike-settings">
            {quoteSpikeSettingsLine(session.pack_settings?.['quote-spike'])}
          </p>
        ) : null}
      </section>

      <section className="bot-strategy__card">
        <h3>LLM decide</h3>
        <p className="form-hint" data-testid="bot-llm-fire-status">
          {llm.live_fire
            ? 'LLM may live-fire when Activate is on.'
            : 'LLM may live-fire when Activate -- currently propose-only or idle.'}
          {llm.configured ? '' : ' Pack is idle until NOVA_LLM_API_KEY, base URL, and model are set.'}
        </p>
        <div className="bot-strategy__grid">
          <label>
            LLM USD cap
            <input
              type="number"
              min={0}
              step={0.25}
              value={llm.usd_cap}
              onChange={e => void patch({ llm: { usd_cap: Number(e.target.value) } })}
            />
          </label>
          <label>
            LLM call cap
            <input
              type="number"
              min={0}
              value={llm.call_cap}
              onChange={e => void patch({ llm: { call_cap: Number(e.target.value) } })}
            />
          </label>
        </div>
        <p className="form-hint">
          Spent ${llm.usd_spent.toFixed(2)} / {llm.calls_used} calls
        </p>
      </section>

      <section className="bot-strategy__card">
        <h3>Advise</h3>
        <label className="bot-strategy__check">
          <input
            type="checkbox"
            checked={session.advise.enabled}
            onChange={e => void patch({ advise: { enabled: e.target.checked } })}
          />
          Enable Advise for the bot (off by default, never places)
        </label>
        <div className="bot-strategy__grid">
          <label>
            USD cap
            <input
              type="number"
              min={0}
              step={0.25}
              value={session.advise.usd_cap}
              onChange={e => void patch({ advise: { usd_cap: Number(e.target.value) } })}
            />
          </label>
          <label>
            Call cap
            <input
              type="number"
              min={0}
              value={session.advise.call_cap}
              onChange={e => void patch({ advise: { call_cap: Number(e.target.value) } })}
            />
          </label>
        </div>
        <p className="form-hint">
          Spent ${session.advise.usd_spent.toFixed(2)} / {session.advise.calls_used} calls
        </p>
      </section>

      <section className="bot-strategy__card">
        <h3>L1 proposals -- human places</h3>
        {pending.length === 0 ? (
          <p className="form-hint">No pending proposals. Accept does not send an order.</p>
        ) : (
          <ul className="bot-strategy__list">
            {pending.map(item => (
              <li key={item.id}>
                <strong>{item.symbol}</strong> {item.side} {item.kind} x{item.preset_qty}
                <span className="form-hint"> -- {item.reason}</span>
                <div className="bot-strategy__row-actions">
                  <button type="button" onClick={() => void resolve(item.id, 'accept')}>
                    Mark accepted
                  </button>
                  <button type="button" onClick={() => void resolve(item.id, 'reject')}>
                    Reject
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="bot-strategy__card">
        <h3>Audit</h3>
        {audit.length === 0 ? (
          <p className="form-hint">No bot audit rows yet.</p>
        ) : (
          <ul className="bot-strategy__audit">
            {audit.slice().reverse().slice(0, 20).map((row, idx) => (
              <li key={`${row.timestamp}-${idx}`}>
                {row.action} · {row.outcome}
                {row.reason ? ` · ${row.reason}` : ''}
                {row.order_id != null ? ` · order ${row.order_id}` : ''}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
