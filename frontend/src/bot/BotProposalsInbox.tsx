/**
 * One inbox for everything that proposes (approved mockup v4, ADR 027): the
 * setup scanner's first-pullback proposals (`/ws/setups`, Stage ticket /
 * Dismiss), the ones it withdrew in the last half hour (the audit stream), and
 * any brain's bot proposals (`/api/bot/proposals`, Mark accepted / Reject).
 * Nothing here places -- Stage ticket fills the Trader ticket and you press Place.
 */
import { useState } from 'react';
import { SETUP_KIND_LABELS, TAPE_VERDICT_TITLES } from '../constants';
import {
  BOTS_PROPOSAL_DISMISS,
  BOTS_PROPOSAL_STAGE,
  BOTS_PROPOSALS_EMPTY,
  BOTS_PROPOSALS_FOOT,
  BOTS_PROPOSALS_SUB,
  BOTS_PROPOSALS_TITLE,
} from '../constantGroups/bots_page';
import { useSetupsBoard } from '../setups/SetupsStreamContext';
import { fmtPx } from '../setups/setupsFormat';
import { stageSetupTicket } from '../setups/stageSetupTicket';
import { closedProposals, proposalWhy, readDismissed, writeDismissed } from './botProposalsModel';
import { etClock, prose } from './botsPageFormat';
import type { BotAuditEntry, BotProposal } from './types';

function kindLabel(kind: string | null | undefined): string {
  return (kind ? SETUP_KIND_LABELS[kind] ?? kind.replace(/_/g, ' ') : 'Setup').toUpperCase();
}

interface Props {
  proposals: BotProposal[];
  audit: BotAuditEntry[];
  resolve: (id: string, action: 'accept' | 'reject') => Promise<unknown>;
  /** Open the Trader on a symbol, pinned, so staging never closes another tab's line. */
  openTrader: (symbol: string) => void;
}

export function BotProposalsInbox({ proposals, audit, resolve, openTrader }: Props) {
  const stream = useSetupsBoard();
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(readDismissed);
  const dismiss = (id: string) => setDismissed(prev => {
    const next = new Set(prev).add(id);
    writeDismissed(next);
    return next;
  });
  const open = (stream?.board?.proposals ?? []).filter(p => p.status === 'open');
  const setups = open.filter(p => !dismissed.has(p.id)).sort((a, b) => b.created_at - a.created_at);
  const rows = new Map((stream?.board?.rows ?? []).map(r => [r.symbol, r]));
  const closed = closedProposals(audit, Date.now() / 1000, new Set(open.map(p => p.id)));
  const pending = proposals.filter(p => p.status === 'pending');
  const count = setups.length + pending.length;

  return (
    <section className="bots-card" data-testid="bots-proposals">
      <header className="bots-card__head">
        <h3>{BOTS_PROPOSALS_TITLE} <span className="bots-count" data-testid="bots-proposals-count">{count} open</span></h3>
        <span className="bots-card__sub">{BOTS_PROPOSALS_SUB}</span>
      </header>
      {count === 0 ? <p className="bots-empty">{BOTS_PROPOSALS_EMPTY}</p> : null}
      {setups.map(p => {
        const tape = p.tape_now ?? 'go';
        const entry = p.entry != null ? p.entry.toFixed(2) : '';
        return (
          <article key={p.id} className="bots-prop" data-testid={`bots-setup-proposal-${p.symbol}`}>
            <div className="bots-prop__head">
              <span className="bots-kind">{kindLabel(p.kind)}</span>
              <b className="bots-prop__sym">{p.symbol}</b>
              <span className="bots-side bots-side--buy">BUY</span>
              <span className="bots-prop__lv">
                trigger <b>{fmtPx(p.trigger)}</b> · stop {fmtPx(p.stop)} · target {fmtPx(p.target1)}
              </span>
              <span className={`bots-vbadge bots-vbadge--${tape}`} title={TAPE_VERDICT_TITLES[tape]}>tape {tape.toUpperCase()}</span>
              {p.grade ? <span className="bots-grade">{p.grade}</span> : null}
            </div>
            <p className="bots-prop__why">{proposalWhy(p, rows.get(p.symbol))}</p>
            <div className="bots-prop__acts">
              <button type="button" className="bots-btn bots-btn--primary" disabled={!entry}
                data-testid={`bots-stage-${p.symbol}`}
                title={`Open ${p.symbol} and stage a BUY limit at ${entry}. Nothing is sent until you press Place.`}
                onClick={() => { stageSetupTicket(p.symbol, entry, openTrader); dismiss(p.id); }}>
                {BOTS_PROPOSAL_STAGE}
              </button>
              <button type="button" className="bots-btn" data-testid={`bots-dismiss-${p.symbol}`} onClick={() => dismiss(p.id)}>
                {BOTS_PROPOSAL_DISMISS}
              </button>
              <span className="bots-prop__time">raised {etClock(p.created_at)} · withdrawn if it re-arms</span>
            </div>
          </article>
        );
      })}
      {closed.map(c => (
        <article key={c.id} className="bots-prop bots-prop--closed" data-testid={`bots-closed-proposal-${c.symbol}`}>
          <div className="bots-prop__head">
            <span className="bots-kind">{kindLabel(c.kind)}</span>
            <b className="bots-prop__sym">{c.symbol}</b>
            <span className="bots-side bots-side--buy">BUY</span>
            <span className="bots-prop__lv">trigger {fmtPx(c.trigger)} · stop {fmtPx(c.stop)}</span>
            <span className="bots-prop__time bots-prop__time--end">{c.label} {etClock(c.closedAt).slice(0, 5)}</span>
          </div>
          {c.reason ? <p className="bots-prop__why">{prose(c.reason.charAt(0).toUpperCase() + c.reason.slice(1))}</p> : null}
        </article>
      ))}
      {pending.map(item => (
        <article key={item.id} className="bots-prop" data-testid={`bots-bot-proposal-${item.id}`}>
          <div className="bots-prop__head">
            <span className="bots-kind">BOT</span>
            <b className="bots-prop__sym">{item.symbol}</b>
            <span className={`bots-side bots-side--${item.side === 'BUY' ? 'buy' : 'sell'}`}>{item.side}</span>
            <span className="bots-prop__lv">{item.kind} × {item.preset_qty}</span>
          </div>
          <p className="bots-prop__why">{prose(item.reason)}</p>
          <div className="bots-prop__acts">
            <button type="button" className="bots-btn" onClick={() => void resolve(item.id, 'accept')}>Mark accepted</button>
            <button type="button" className="bots-btn" onClick={() => void resolve(item.id, 'reject')}>Reject</button>
            <span className="bots-prop__time">Accept does not send an order</span>
          </div>
        </article>
      ))}
      <p className="bots-foot-note">ⓘ {BOTS_PROPOSALS_FOOT}</p>
    </section>
  );
}
