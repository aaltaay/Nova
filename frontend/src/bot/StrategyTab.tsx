import { BOT_ACTION_KINDS, BOT_LEVEL_LABELS } from '../constantGroups/bot';
import { useBotSession } from './useBotSession';

export function StrategyTab() {
  const { session, proposals, audit, error, busy, patch, resolve } = useBotSession();

  if (!session) {
    return <div className="bot-strategy empty-state">{error || 'Loading bot session…'}</div>;
  }

  const pending = proposals.filter(p => p.status === 'pending');

  return (
    <div className="bot-strategy">
      <header className="bot-strategy__header">
        <div>
          <h2>Strategy -- small-cap</h2>
          <p className="form-hint">
            Brain stays outside Nova. This desk owns risk, allowlist, and the only order door.
            L3 Unrestricted is parked. Advise never places.
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
          Desk can still trade. Re-enable L2 only if you mean it.
          <button
            type="button"
            className="bot-strategy__btn"
            onClick={() => void patch({ reenable: true, level: 2 })}
          >
            Re-enable Strategy
          </button>
        </div>
      ) : null}

      <section className="bot-strategy__card">
        <h3>Autonomy</h3>
        <div className="bot-strategy__levels">
          {([0, 1, 2] as const).map(level => (
            <label key={level}>
              <input
                type="radio"
                name="bot-level"
                checked={session.level === level}
                onChange={() => void patch({ level })}
              />
              {BOT_LEVEL_LABELS[level]}
            </label>
          ))}
          <label className="bot-strategy__disabled">
            <input type="radio" disabled />
            L3 Unrestricted -- parked (#216)
          </label>
        </div>
        <p className="form-hint">
          Brain session: {session.brain_session_id || 'none'} · strategy:{' '}
          {session.strategy || 'off'}
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
          Allowlist: {BOT_ACTION_KINDS.join(', ')}. Free-form qty is refused.
          New buys block while a bot working order exists.
        </p>
        <p className="form-hint">
          Live L2 (max 3, shared with Trader): {session.trader_live.join(', ') || 'none'}
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
