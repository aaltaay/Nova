/**
 * The plan on top of Level 2 (ADR 036): the leading setup's entry, stop and 2:1 target -- or the
 * operator's own when nothing is forming -- with the risk, the size the venue sleeve's risk per trade
 * buys, a ruler of what stands between and the checks. Its buttons follow who trades the stock (ADR 037):
 * Signal only stages the ticket (a BUY limit at the entry, or a sell once shares are held) and never
 * places; Approve approves the plan, or buys now after the trigger; Auto-entry and Bot turn off; and
 * whenever Nova holds the exits, the operator can take them over. In a Nova mode it says the size Nova
 * sends, and NOT A TRADE says it blocks Nova's buys too.
 */
import { useEffect, useState } from 'react';
import { tickerLastTrade } from '../hooks/tickerStore';
import { useTickerSelect } from '../hooks/useTickerStream';
import { requestOrderTicketPrefill, useOrderTicketListening } from '../ibkr';
import { riskSourceWords } from '../setups';
import { tipProps, whyProps } from '../ux';
import { NOT_A_TRADE_NOVA } from './constants';
import { novaSizeWords } from './novaPromise';
import { EmptyPlan } from './PlanEmpty';
import { PlanNumbers } from './PlanNumbers';
import { PlanLevels } from './PlanLevels';
import { PlanChecks, PlanRuler } from './PlanRuler';
import { ShortPlanChecks } from './ShortPlanChecks';
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
import { liquidityTip } from '../setups';
import { HeldCard } from './HeldCard';
import { heldAnyQty } from './momentShort';
import { gradeChip, gradeTip, notATrade, thinPlan } from './planVerdict';
import type { StockReadContextValue } from './StockReadContext';
import type { StockPlan } from './types';
import { planActions, type PlanAction } from './planActions';
import { modeSentence } from './whoTradesModel';
import './whoTrades.css';
import './shortRead.css';

const STAGED_NOTE_MS = 8_000;

const SHORT_PLAN_TIP = 'A short plan (ADR 048): sell at the entry, a buy stop over it, cover at entry - 2R. Shorts '
  + 'go out with their buy stop on Paper and Sim; Nova covers what is left at 15:55 ET.';

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

/** In a Nova mode, the size Nova sends for the plan and why (spec E); nothing in Signal only. */
function NovaSizeLine({ ctx }: { ctx: StockReadContextValue }) {
  const view = ctx.who.view;
  if (!view || view.mode === 'signal') return null;
  const words = novaSizeWords(view.size);
  if (!words) return null;
  return (
    <p className={`sr-plan__nova-size${words.skip ? ' sr-plan__nova-size--skip' : ''}`}
      {...tipProps(words.tip, 'The size Nova sends')} data-testid="stock-read-nova-size">
      {words.text}
    </p>
  );
}

/** The risk per trade's trouble: not saved, not moved, not the sleeve's, or the sleeve's last read failed
 * (its last good value still sizes). Nothing when all is well. */
function riskTrouble(ctx: StockReadContextValue): string | null {
  const r = ctx.risk;
  return r.saveError ?? r.moveError ?? r.why;
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
  const bid = ctx.topOfBook?.bid ?? null;
  // A sell with no bid to price it falls back to the last trade, read only then: the stock read's inputs
  // carry no price, so a print does not render the plan (#707).
  const lastNoBid = useTickerSelect(ctx.symbol, (state) =>
    (bid === null ? tickerLastTrade(state, ctx.symbol)?.price ?? null : null));

  if (!read) return null;
  const mode = ctx.layers.plan;
  const folded = mode === 'folded' || (mode === 'auto' && !roomy);
  // While you hold the stock the box is the trade's (ADR 036 amendment 2026-10-01), folded the same way.
  if (read.held && heldAnyQty(ctx.who.inputs) > 0) {
    return <HeldCard ctx={ctx} held={read.held} folded={folded}
      onFold={() => ctx.setLayers({ plan: folded ? 'open' : 'folded' })} />;
  }
  const lane = planLane(plan, read.setups);
  const manual = plan?.source === 'manual' || plan === null;
  const foldTip = !folded ? 'Fold the plan to one line'
    : mode === 'auto' ? 'One line while Level 2 needs the room: open the whole plan' : 'Open the whole plan';
  const name = plan && plan.source === 'setup' ? setupName(plan.setup_type) : 'Your plan';
  const grade = plan && plan.source === 'setup' ? gradeChip(plan) : null;
  const size = plan ? sizeFor(ctx.riskUsd, plan.risk) : null;
  // Not a trade: Stage and Approve say why instead of acting (operator report, 2026-09-29).
  const noTrade = notATrade(plan);
  const locked = plan ? (noTrade ?? stageLock(plan, size, ctx.riskUsd, listening)) : 'No plan yet.';
  const short = plan?.side === 'short';
  const stage = () => {
    if (!plan || locked || plan.entry === null || size === null) return;
    // A short stages on the ticket's Short side with the plan's buy stop (ADR 048): it never goes out without one.
    requestOrderTicketPrefill({
      symbol: ctx.symbol,
      side: short ? 'SELL' : 'BUY',
      orderType: 'LMT',
      quantityValue: String(size),
      limitPrice: fmtPx(plan.entry),
      ...(short && plan.stop !== null ? { shortEntry: true, buyStop: fmtPx(plan.stop) } : {}),
    });
    // Where the size came from, said with it: the sleeve's risk per trade (or the stated fallback).
    const sized = `$${ctx.riskUsd} of risk (${riskSourceWords(ctx.risk)} risk per trade) over `
      + `${fmtStep(plan.risk, plan.entry)} a share.`;
    setStaged(short
      ? `Staged SHORT ${size} LMT ${fmtPx(plan.entry)} with its buy stop ${fmtPx(plan.stop)}: ${sized} The cover `
        + `${fmtPx(plan.target)} is yours to set.`
      : `Staged BUY ${size} LMT ${fmtPx(plan.entry)}: ${sized} Set the stop ${fmtPx(plan.stop)} and the target `
        + `${fmtPx(plan.target)} yourself: the ticket takes no bracket from the plan.`);
  };
  const who = ctx.who;
  const whoMode = who.view?.mode ?? 'signal';
  // The folded line keeps Nova's size beside yours in a Nova mode, so folding hides neither.
  const novaSize = whoMode !== 'signal' ? who.view?.size ?? null : null;
  const novaFolded = novaSize ? (novaSize.qty >= 1 ? Math.floor(novaSize.qty).toLocaleString('en-US') : 'none') : null;
  const trouble = riskTrouble(ctx);
  const { actions, status } = planActions({
    moment: who.moment,
    inputs: lastNoBid === null ? who.inputs : { ...who.inputs, last: lastNoBid },
    bid,
    listening,
    stageLocked: locked,
    notTrade: noTrade,
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
      className={`sr-plan sr-plan--${plan?.state ?? 'none'}${plan?.provisional ? ' sr-plan--provisional' : ''}${
        noTrade ? ' sr-plan--notrade' : ''}`}
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
        {short && <span className="sr-plan__side" {...tipProps(SHORT_PLAN_TIP, 'Short')}
          data-testid="stock-read-plan-short">SHORT</span>}
        {!folded && <span className="sr-plan__name">{name}</span>}
        {plan && grade && (
          <span className={`sr-plan__grade sr-plan__grade--${plan.grade}`} {...tipProps(gradeTip(plan), `Grade ${grade}`)}
            data-testid="stock-read-plan-grade">
            {grade}
          </span>
        )}
        <span
          className={`sr-plan__badge sr-plan__badge--${plan?.result ? `result-${plan.result.outcome}`
            : noTrade ? 'notrade' : plan?.state ?? 'manual'}`}
          {...tipProps(plan?.result ? `It played out: ${plan.result.text}.` : plan?.reason, name)}
          data-testid="stock-read-plan-badge"
        >
          {!plan ? 'NO SETUP' : folded ? planBadgeShort(plan, lane) : planBadge(plan, lane)}
        </span>
        {plan && thinPlan(plan) && plan.liquidity ? (
          // Too thin to trade (2026-10-01): said even after it played out -- nobody could have traded it.
          <span className="sr-plan__verdict sr-plan__verdict--thin"
            {...tipProps(`${liquidityTip(plan.liquidity)}\n${NOT_A_TRADE_NOVA}`, 'Too thin to trade')}
            data-testid="stock-read-plan-verdict">
            TOO THIN
          </span>
        ) : noTrade && !plan?.result && (
          <span className="sr-plan__verdict" {...tipProps(`${noTrade}\n${NOT_A_TRADE_NOVA}`, 'Not a trade')}
            data-testid="stock-read-plan-verdict">
            NOT A TRADE
          </span>
        )}
        {folded && plan && (
          <span className="sr-plan__folded" data-testid="stock-read-plan-line"
            {...tipProps(`${short ? 'Short at / buy stop / cover' : 'Entry / stop / target'} · your size${
              novaFolded ? ' · the size Nova sends' : ''}`, 'The plan')}>
            {fmtPx(plan.entry)}/{fmtPx(plan.stop)}/{fmtPx(plan.target)}
            {size !== null ? ` · ${size.toLocaleString('en-US')} sh` : ''}
            {novaFolded ? ` · Nova ${novaFolded}` : ''}
          </span>
        )}
        {folded && !plan && (
          <span className="sr-plan__folded sr-plan__folded--muted" data-testid="stock-read-plan-line">
            nothing forming · open to plan a hand trade
          </span>
        )}
        {(plan || !folded) && !noTrade && (
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
          {noTrade && (
            <p className="sr-plan__notrade" data-testid="stock-read-plan-notrade">{noTrade} {NOT_A_TRADE_NOVA}</p>
          )}
          {plan ? (
            <PlanNumbers
              plan={plan}
              risk={ctx.risk}
              onRiskUsd={ctx.setRiskUsd}
              onManual={manual ? ctx.setManualPlan : null}
              manualStop={ctx.manual.stop}
            />
          ) : (
            <EmptyPlan ctx={ctx} read={read} />
          )}
          {plan && <NovaSizeLine ctx={ctx} />}
          {plan && trouble && (
            <p className="sr-plan__risk-note" {...tipProps(trouble, 'Risk per trade')} data-testid="stock-read-risk-note">
              {trouble}
            </p>
          )}
          {plan && <PlanRuler plan={plan} price={read.price} />}
          {plan && <PlanLevels plan={plan} />}
          {plan && <PlanChecks plan={plan} />}
          {plan && <ShortPlanChecks symbol={ctx.symbol} plan={plan} size={size} />}
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
              onClick={() => ctx.setLayers(ctx.layers.setups ? { setups: false } : { eyes: true, setups: true })}
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
