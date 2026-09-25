/**
 * The plan on top of Level 2 (ADR 036): the leading setup's entry, stop and 2:1 target -- or the
 * operator's own when nothing is forming -- with the risk, the size their risk per trade buys, a
 * ruler of what stands between and the checks. Its buttons follow who trades the stock (ADR 037):
 * Signal only stages the ticket (a BUY limit at the entry, or a sell once shares are held) and never
 * places; Approve approves the plan, or buys now after the trigger; Auto-entry and Bot at Strategy
 * turn off; and whenever Nova holds the exits, the operator can take them over.
 */
import { useEffect, useState } from 'react';
import { requestOrderTicketPrefill, useOrderTicketListening } from '../ibkr';
import { tipProps, whyProps } from '../ux';
import { PlanNumbers } from './PlanNumbers';
import { PlanChecks, PlanRuler } from './PlanRuler';
import {
  fmtPx,
  fmtStep,
  planBadge,
  planBadgeShort,
  planFootnote,
  planLane,
  rrText,
  setupName,
  sizeFor,
} from './planMath';
import type { StockReadContextValue } from './StockReadContext';
import type { StockPlan, StockRead } from './types';
import { modeSentence, planActions, type PlanAction } from './whoTradesModel';
import './whoTrades.css';

const STAGED_NOTE_MS = 8_000;

/** The folded line's word for an action. */
const SHORT: Record<PlanAction['id'], string> = {
  stage: 'Stage',
  'stage-sell': 'Stage sell',
  approve: 'Approve',
  'approve-now': 'Buy now',
  'cancel-approval': 'Cancel',
  'take-over': 'Take over',
  'auto-off': 'Auto-entry off',
  'bot-off': 'Bot off',
};

function stageLock(plan: StockPlan, size: number | null, riskUsd: number, listening: boolean): string | null {
  if (plan.entry === null) return 'The plan has no entry yet.';
  if (plan.stop === null) return 'Name a stop first: the size comes from the risk to it.';
  if (size === null) return `$${riskUsd} of risk buys no whole share at ${fmtStep(plan.risk, plan.entry)} a share.`;
  if (!listening) return 'This tab has no order ticket open to fill. Show the Order Entry module on the rail.';
  return null;
}

function EmptyPlan({ ctx, read }: { ctx: StockReadContextValue; read: StockRead }) {
  const ask = ctx.topOfBook?.ask ?? null;
  const [text, setText] = useState('');
  const commit = () => {
    const n = Number(text.replace(/[$,\s]/g, ''));
    if (Number.isFinite(n) && n > 0) ctx.setManualPlan(n, null);
  };
  const why = read.followed ? 'No setup is forming on it.' : (read.followed_note ?? 'The setup scanner does not follow it.');
  return (
    <div className="sr-plan__empty" data-testid="stock-read-plan-empty">
      <span className="sr-plan__empty-why">{why} Plan a hand trade at 2:1:</span>
      <button
        type="button"
        className="sr-btn"
        disabled={ask === null}
        {...whyProps(ask === null, 'No ask on Level 2 yet.')}
        onClick={() => ask !== null && ctx.setManualPlan(ask, null)}
        data-testid="stock-read-entry-ask"
      >
        Entry at the ask {ask === null ? '' : fmtPx(ask)}
      </button>
      <input
        className="sr-num__input sr-plan__empty-input"
        inputMode="decimal"
        aria-label="Your entry"
        placeholder="or type an entry"
        value={text}
        onChange={e => setText(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter') commit();
          e.stopPropagation();
        }}
        onBlur={commit}
        data-testid="stock-read-entry-type"
      />
    </div>
  );
}

export function PlanCard({ ctx, roomy = true }: {
  ctx: StockReadContextValue;
  /** The quote card has room for the whole plan and Level 2 (the plan's `auto` mode reads it). */
  roomy?: boolean;
}) {
  const read = ctx.read.data;
  const plan = read?.plan ?? null;
  const listening = useOrderTicketListening(ctx.symbol);
  const [staged, setStaged] = useState<string | null>(null);
  useEffect(() => {
    if (!staged) return;
    const id = window.setTimeout(() => setStaged(null), STAGED_NOTE_MS);
    return () => window.clearTimeout(id);
  }, [staged]);

  if (!read) return null;
  const lane = planLane(plan, read.setups);
  const manual = plan?.source === 'manual' || plan === null;
  const mode = ctx.layers.plan;
  const folded = mode === 'folded' || (mode === 'auto' && !roomy);
  const foldTip = !folded ? 'Fold the plan to one line'
    : mode === 'auto' ? 'One line while Level 2 needs the room: open the whole plan' : 'Open the whole plan';
  const name = plan && plan.source === 'setup'
    ? `${setupName(plan.setup_type)}${plan.grade ? ` · grade ${plan.grade}` : ''}`
    : 'Your plan';
  const size = plan ? sizeFor(ctx.riskUsd, plan.risk) : null;
  const locked = plan ? stageLock(plan, size, ctx.riskUsd, listening) : 'No plan yet.';
  const stage = () => {
    if (!plan || locked || plan.entry === null || size === null) return;
    requestOrderTicketPrefill({
      symbol: ctx.symbol,
      side: 'BUY',
      orderType: 'LMT',
      quantityValue: String(size),
      limitPrice: fmtPx(plan.entry),
    });
    setStaged(`Staged BUY ${size} LMT ${fmtPx(plan.entry)}. Set the stop ${fmtPx(plan.stop)} and the target `
      + `${fmtPx(plan.target)} yourself: the ticket takes no bracket from the plan.`);
  };
  const who = ctx.who;
  const whoMode = who.view?.mode ?? 'signal';
  const { actions, status } = planActions({
    moment: who.moment,
    inputs: who.inputs,
    bid: ctx.topOfBook?.bid ?? null,
    listening,
    stageLocked: locked,
    symbol: ctx.symbol,
  });
  const act = (a: PlanAction) => {
    switch (a.id) {
      case 'stage':
        return stage();
      case 'stage-sell':
        if (!a.sell) return;
        requestOrderTicketPrefill({
          symbol: ctx.symbol,
          side: 'SELL',
          orderType: 'LMT',
          quantityValue: String(a.sell.qty),
          limitPrice: fmtPx(a.sell.price),
        });
        return setStaged(`Staged SELL ${a.sell.qty} LMT ${fmtPx(a.sell.price)}. Nothing is sent until you send it.`);
      case 'approve':
        return void who.approve(false);
      case 'approve-now':
        return void who.approve(true);
      case 'cancel-approval':
        return void who.withdraw();
      case 'take-over':
        return void who.takeOver();
      case 'auto-off':
        return void who.setSides('you', who.view?.sell ?? 'you');
      case 'bot-off':
        return void who.setSides('you', 'you');
    }
  };
  const lockOf = (a: PlanAction) => a.locked ?? (a.id !== 'stage' && a.id !== 'stage-sell' ? who.busy : null);
  const actionButton = (a: PlanAction, folded: boolean) => {
    const why = lockOf(a);
    const testId = a.id === 'stage' ? (folded ? 'stock-read-stage-line' : 'stock-read-stage')
      : `stock-read-action-${a.id}${folded ? '-line' : ''}`;
    return (
      <button
        key={a.id}
        type="button"
        className={`sr-btn sr-btn--${a.tone === 'plain' ? 'plain' : a.tone}${folded ? ' sr-btn--small' : ''}`}
        disabled={why !== null}
        {...whyProps(why !== null, why)}
        {...(why === null ? tipProps(a.tip) : {})}
        onClick={() => act(a)}
        data-testid={testId}
      >
        {folded ? SHORT[a.id] : a.label}
      </button>
    );
  };
  const note = staged
    ?? (whoMode === 'signal' ? (plan ? planFootnote(plan, lane) : '') : modeSentence(whoMode, ctx.symbol));

  return (
    <section
      className={`sr-plan sr-plan--${plan?.state ?? 'none'}${plan?.provisional ? ' sr-plan--provisional' : ''}`}
      data-testid="stock-read-plan"
      aria-label="The plan"
    >
      <header className="sr-plan__head">
        <button
          type="button"
          className="sr-plan__fold"
          aria-expanded={!folded}
          onClick={() => ctx.setLayers({ plan: folded ? 'open' : 'folded' })}
          {...tipProps(foldTip)}
          data-testid="stock-read-plan-fold"
        >
          {folded ? '▸' : '▾'}
        </button>
        {!folded && <span className="sr-plan__kicker">Plan</span>}
        {!folded && <span className="sr-plan__name">{name}</span>}
        <span className={`sr-plan__badge sr-plan__badge--${plan?.state ?? 'manual'}`} {...tipProps(plan?.reason, name)}>
          {!plan ? 'NO SETUP' : folded ? planBadgeShort(plan, lane) : planBadge(plan, lane)}
        </span>
        {folded && plan && (
          <span className="sr-plan__folded" data-testid="stock-read-plan-line"
            {...tipProps('Entry / stop / target', 'The plan')}>
            {fmtPx(plan.entry)}/{fmtPx(plan.stop)}/{fmtPx(plan.target)}
            {size !== null ? ` · ${size.toLocaleString('en-US')} sh` : ''}
          </span>
        )}
        {folded && !plan && (
          <span className="sr-plan__folded sr-plan__folded--muted" data-testid="stock-read-plan-line">
            nothing forming · open to plan a hand trade
          </span>
        )}
        {(plan || !folded) && (
          <span className="sr-plan__rr" {...tipProps(plan?.target_rule, 'Reward to risk')}>
            <b>{rrText(plan?.rr ?? null)}</b>
            {!folded && <span className="sr-plan__rr-k"> reward : risk</span>}
          </span>
        )}
        {folded && (plan || actions[0]?.id !== 'stage') && actions[0] && actionButton(actions[0], true)}
      </header>
      {folded && staged && <p className="sr-plan__note sr-plan__note--line">{staged}</p>}
      {!folded && (
        <>
          {plan ? (
            <PlanNumbers
              plan={plan}
              riskUsd={ctx.riskUsd}
              onRiskUsd={ctx.setRiskUsd}
              onManual={manual ? ctx.setManualPlan : null}
              manualStop={ctx.manual.stop}
            />
          ) : (
            <EmptyPlan ctx={ctx} read={read} />
          )}
          {plan && <PlanRuler plan={plan} price={read.price} />}
          {plan && <PlanChecks plan={plan} />}
          <footer className="sr-plan__foot">
            {status && (
              <span
                className={`sr-plan__status sr-plan__status--${status.startsWith('Closed · -') ? 'stop' : 'done'}`}
                data-testid="stock-read-plan-status"
              >
                {status}
              </span>
            )}
            {actions.map(a => actionButton(a, false))}
            <button
              type="button"
              className="sr-btn"
              aria-pressed={ctx.layers.setups}
              onClick={() => ctx.setLayers({ setups: !ctx.layers.setups })}
              {...tipProps('Draw the setups and the plan\'s entry, stop and target on the charts.')}
              data-testid="stock-read-show-on-chart"
            >
              Show on chart {ctx.layers.setups ? '✓' : ''}
            </button>
            {ctx.manual.entry !== null && (
              <button
                type="button"
                className="sr-btn sr-btn--quiet"
                onClick={() => ctx.setManualPlan(null, null)}
                data-testid="stock-read-clear-manual"
              >
                Clear my plan
              </button>
            )}
            <span className="sr-plan__note" data-testid="stock-read-plan-note">
              {note}
            </span>
          </footer>
        </>
      )}
    </section>
  );
}
