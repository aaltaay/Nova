/**
 * One inbox for everything that proposes (approved mockup v4, ADR 027, ADR 031):
 * every setup at Eyes raises proposals on the setup scanner (`/ws/setups`, Stage
 * ticket / Dismiss) -- one card per symbol, naming every setup that raised one --
 * the ones it withdrew in the last half hour (the audit stream), and any brain's
 * bot proposals (`/api/bot/proposals`, Mark accepted / Reject). Nothing here
 * places -- Stage ticket fills the Trader ticket and you press Place.
 */
import { useState } from 'react';
import { SETUP_KIND_LABELS } from '../constants';
import {
  BOTS_PROPOSAL_DISMISS,
  BOTS_PROPOSAL_STAGE,
  BOTS_PROPOSALS_EMPTY,
  BOTS_PROPOSALS_FOOT,
  BOTS_PROPOSALS_SUB,
  BOTS_PROPOSALS_TITLE,
} from '../constantGroups/bots_page';
import { SETUPS_STAGE_NO_ENTRY_WHY, TAPE_VERDICT_TIPS } from '../constantGroups/setups';
import {
  fmtPx,
  setupLabel,
  setupTypeOf,
  stageSetupTicket,
  useSetupsBoard,
  type SetupProposal,
  type SetupRow,
} from '../setups';
import { tipProps } from '../ux/hoverTip';
import { closedProposals, proposalWhy, readDismissed, writeDismissed } from './botProposalsModel';
import { etClock, prose } from './botsPageFormat';
import type { BotAuditEntry, BotProposal } from './types';

function kindLabel(kind: string | null | undefined): string {
  return (kind ? SETUP_KIND_LABELS[kind] ?? kind.replace(/_/g, ' ') : 'Setup').toUpperCase();
}

/** Open proposals by symbol, newest first; a symbol's newest proposal leads its card. */
function bySymbol(open: readonly SetupProposal[]): SetupProposal[][] {
  const groups = new Map<string, SetupProposal[]>();
  for (const p of [...open].sort((a, b) => b.created_at - a.created_at)) {
    const list = groups.get(p.symbol);
    if (list) list.push(p);
    else groups.set(p.symbol, [p]);
  }
  return [...groups.values()];
}

function rowFor(rows: readonly SetupRow[], p: SetupProposal): SetupRow | undefined {
  const type = setupTypeOf(p);
  return rows.find(r => r.symbol === p.symbol && setupTypeOf(r) === type);
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
  const dismissAll = (ids: readonly string[]) => setDismissed(prev => {
    const next = new Set(prev);
    ids.forEach(id => next.add(id));
    writeDismissed(next);
    return next;
  });
  const open = (stream?.board?.proposals ?? []).filter(p => p.status === 'open');
  const groups = bySymbol(open.filter(p => !dismissed.has(p.id)));
  const rows = stream?.board?.rows ?? [];
  const closed = closedProposals(audit, Date.now() / 1000, new Set(open.map(p => p.id)));
  const pending = proposals.filter(p => p.status === 'pending');
  const count = groups.length + pending.length;

  return (
    <section className="bots-card" data-testid="bots-proposals">
      <header className="bots-card__head">
        <h3>{BOTS_PROPOSALS_TITLE} <span className="bots-count" data-testid="bots-proposals-count">{count} open</span></h3>
        <span className="bots-card__sub">{BOTS_PROPOSALS_SUB}</span>
      </header>
      {count === 0 ? <p className="bots-empty">{BOTS_PROPOSALS_EMPTY}</p> : null}
      {groups.map(([p, ...also]) => {
        const tape = p.tape_now ?? 'go';
        const entry = p.entry != null ? p.entry.toFixed(2) : '';
        const ids = [p.id, ...also.map(a => a.id)];
        return (
          <article key={p.id} className="bots-prop" data-testid={`bots-setup-proposal-${p.symbol}`}>
            <div className="bots-prop__head">
              <span className="bots-kind" {...tipProps(`Raised by the ${setupLabel(setupTypeOf(p))} scanner${p.template_name ? ` (template ${p.template_name})` : ''}.`)}>
                {kindLabel(p.kind)}
              </span>
              <b className="bots-prop__sym">{p.symbol}</b>
              <span className="bots-side bots-side--buy">BUY</span>
              <span className="bots-prop__lv">
                trigger <b>{fmtPx(p.trigger)}</b> · stop {fmtPx(p.stop)} · target {fmtPx(p.target1)}
              </span>
              <span className={`bots-vbadge bots-vbadge--${tape}`} {...tipProps(TAPE_VERDICT_TIPS[tape] ?? tape, 'The tape now')}>tape {tape.toUpperCase()}</span>
              {p.grade ? <span className="bots-grade">{p.grade}</span> : null}
            </div>
            <p className="bots-prop__why">{proposalWhy(p, rowFor(rows, p))}</p>
            {also.length ? (
              <p className="bots-prop__also" data-testid={`bots-setup-proposal-also-${p.symbol}`}>
                Also proposed by {also.map(a => `${setupLabel(setupTypeOf(a))} (trigger ${fmtPx(a.trigger)}, stop ${fmtPx(a.stop)})`).join(' · ')}
              </p>
            ) : null}
            <div className="bots-prop__acts">
              <button type="button" className="bots-btn bots-btn--primary" disabled={!entry}
                data-testid={`bots-stage-${p.symbol}`}
                data-why={entry ? undefined : SETUPS_STAGE_NO_ENTRY_WHY}
                title={entry ? `Open ${p.symbol} and stage a BUY limit at ${entry}. Nothing is sent until you press Place.` : undefined}
                onClick={() => { stageSetupTicket(p.symbol, entry, openTrader); dismissAll(ids); }}>
                {BOTS_PROPOSAL_STAGE}
              </button>
              <button type="button" className="bots-btn" data-testid={`bots-dismiss-${p.symbol}`} onClick={() => dismissAll(ids)}>
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
