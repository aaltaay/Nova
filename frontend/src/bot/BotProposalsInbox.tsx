/**
 * One inbox for everything that proposes (ADR 027): the setup scanner's
 * first-pullback proposals (`/ws/setups`, Stage ticket / Dismiss) and any
 * brain's bot proposals (`/api/bot/proposals`, Mark accepted / Reject). Nothing
 * here places -- Stage ticket fills the Trader ticket and you press Place.
 */
import { useState } from 'react';
import { SETUP_KIND_LABELS, TAPE_VERDICT_LABELS, TAPE_VERDICT_TITLES } from '../constants';
import { useSetupsBoard } from '../setups/SetupsStreamContext';
import { fmtPx } from '../setups/setupsFormat';
import { stageSetupTicket } from '../setups/stageSetupTicket';
import { useWorkspace } from '../workspace/WorkspaceContext';
import type { BotProposal } from './types';

function clock(ts: number | null | undefined): string {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour12: false });
}

export function BotProposalsInbox({ proposals, resolve }: {
  proposals: BotProposal[];
  resolve: (id: string, action: 'accept' | 'reject') => Promise<unknown>;
}) {
  const stream = useSetupsBoard();
  const { openStockView } = useWorkspace();
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(() => new Set());
  const setups = (stream?.board?.proposals ?? [])
    .filter(p => p.status === 'open' && !dismissed.has(p.id))
    .sort((a, b) => b.created_at - a.created_at);
  const pending = proposals.filter(p => p.status === 'pending');
  const count = setups.length + pending.length;

  return (
    <section className="bots-card" data-testid="bots-proposals">
      <header className="bots-card__head">
        <h3>Proposals <span className="bots-count">{count} open</span></h3>
        <span className="bots-card__sub">nothing here places · you press Place</span>
      </header>
      {count === 0 ? (
        <p className="bots-empty">
          No open proposals. The scanner raises one when a first pullback is near its trigger and the tape says go.
        </p>
      ) : null}
      {setups.map(p => {
        const tape = p.tape_now ?? 'go';
        const entry = p.entry != null ? p.entry.toFixed(2) : '';
        return (
          <article key={p.id} className="bots-prop" data-testid={`bots-setup-proposal-${p.symbol}`}>
            <div className="bots-prop__head">
              <span className="bots-prop__kind">{(p.kind ? SETUP_KIND_LABELS[p.kind] ?? p.kind : 'Setup').toUpperCase()}</span>
              <b>{p.symbol}</b>
              <span className="bots-buy">BUY</span>
              <span className="bots-prop__lv">
                trigger {fmtPx(p.trigger)} · stop {fmtPx(p.stop)} · target {fmtPx(p.target1)}
              </span>
              <span className={`setups-tape--${tape}`} title={TAPE_VERDICT_TITLES[tape]}>{TAPE_VERDICT_LABELS[tape] ?? tape}</span>
              {p.grade ? <span className="bots-grade">{p.grade}</span> : null}
            </div>
            {p.reasons?.length ? <p className="bots-prop__why">{p.reasons.join(' · ')}</p> : null}
            <div className="bots-prop__acts">
              <button type="button" className="bots-btn bots-btn--primary" disabled={!entry}
                title={`Open ${p.symbol} and stage a BUY limit at ${entry}. Nothing is sent until you press Place.`}
                onClick={() => { stageSetupTicket(p.symbol, entry, openStockView); setDismissed(prev => new Set(prev).add(p.id)); }}>
                Stage ticket
              </button>
              <button type="button" className="bots-btn" onClick={() => setDismissed(prev => new Set(prev).add(p.id))}>
                Dismiss
              </button>
              <span className="bots-muted">raised {clock(p.created_at)} · withdrawn if it re-arms</span>
            </div>
          </article>
        );
      })}
      {pending.map(item => (
        <article key={item.id} className="bots-prop" data-testid={`bots-bot-proposal-${item.id}`}>
          <div className="bots-prop__head">
            <span className="bots-prop__kind">BOT</span>
            <b>{item.symbol}</b>
            <span className={item.side === 'BUY' ? 'bots-buy' : 'bots-sell'}>{item.side}</span>
            <span className="bots-prop__lv">{item.kind} × {item.preset_qty}</span>
          </div>
          <p className="bots-prop__why">{item.reason}</p>
          <div className="bots-prop__acts">
            <button type="button" className="bots-btn" onClick={() => void resolve(item.id, 'accept')}>Mark accepted</button>
            <button type="button" className="bots-btn" onClick={() => void resolve(item.id, 'reject')}>Reject</button>
            <span className="bots-muted">Accept does not send an order</span>
          </div>
        </article>
      ))}
      <p className="bots-muted">ⓘ Proposals pop up on every tab; this is where they're kept.</p>
    </section>
  );
}
