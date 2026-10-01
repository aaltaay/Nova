/**
 * The plan box while you hold the stock (ADR 036 amendment 2026-10-01; operator on mockup v4b: keep the
 * plan box, "i like that bar ... but i also really like the 'then' 'next' 'now' 'broke'"). The same box --
 * header, five numbers, ruler, level rows, checks, buttons -- about your position and measured from the
 * price, with the ladder under the ruler. Its stop is yours to set (never an order); "Nova takes the exit"
 * hands Nova the sell (Paper and Sim; `ExitSheet`).
 */
import { requestOrderTicketPrefill, useOrderTicketListening } from '../ibkr';
import { tipProps, whyProps } from '../ux';
import { ExitSheet } from './ExitSheet';
import { ROLE_WORDS, rowOf, stopWords, type StockHeld } from './heldRead';
import { heldRuler } from './heldView';
import { fmtPnl } from './momentModel';
import { LevelRowList } from './PlanLevels';
import { PriceInput } from './PlanNumbers';
import { CheckList, useWidth } from './PlanRuler';
import { fmtPx } from './planMath';
import type { StockReadContextValue } from './StockReadContext';
import { HELD_LIVE_EXIT_WHY } from './whoTradesModel';
import './heldTrade.css';

function HeldRuler({ held }: { held: StockHeld }) {
  const [ref, width] = useWidth();
  const lay = heldRuler(held, width);
  if (!lay) return null;
  const seg = (cls: string, s: [number, number] | null) => s && (
    <span className={cls} style={{ left: `${s[0]}%`, width: `${s[1] - s[0]}%` }} />
  );
  return (
    <div ref={ref} className="sr-ruler sr-ruler--held" data-testid="held-ruler" aria-hidden="true">
      {seg('sr-ruler__locked', lay.locked)}
      {seg('sr-ruler__risk', lay.risk)}
      {seg('sr-ruler__reward', lay.reward)}
      {seg('sr-ruler__ahead', lay.ahead)}
      {lay.marks.map(m => (
        <span key={`${m.kind}-${m.label}`} className={`sr-ruler__mark sr-ruler__mark--${m.kind}`} style={{ left: `${m.pct}%` }}>
          {m.showLabel && <span className="sr-ruler__mark-label">{m.label}</span>}
        </span>
      ))}
      {lay.stopPct !== null && <span className="sr-ruler__end sr-ruler__end--stop" style={{ left: `${lay.stopPct}%` }} />}
      <span className="sr-ruler__end sr-ruler__end--target" style={{ left: `${lay.endPct}%` }} />
      <span className="sr-ruler__entry" style={{ left: `${lay.costPct}%` }} {...tipProps(`Your average ${fmtPx(held.avg)}`)} />
      {lay.nowPct !== null && <span className="sr-ruler__now" style={{ left: `${lay.nowPct}%` }} />}
    </div>
  );
}

function HeldLadder({ held }: { held: StockHeld }) {
  return (
    <ul className="sr-ladder" data-testid="held-ladder" aria-label="The levels over and under the price">
      {held.ladder.map((r, i) => (
        <li key={`${r.role}-${r.price}-${i}`} className={`sr-ladder__row sr-ladder__row--${r.role}`}
          {...tipProps(r.text, `${ROLE_WORDS[r.role]} ${fmtPx(r.price)}`)}>
          <span className="sr-ladder__p">{fmtPx(r.price)}</span>
          <span className="sr-ladder__c">{ROLE_WORDS[r.role]}</span>
          <span className="sr-ladder__t">{r.text}</span>
          <span className="sr-ladder__r">
            {r.role === 'stop' || r.role === 'now' ? fmtPnl(r.usd) : ''}
            {r.r !== null && r.role !== 'cost' ? `${r.role === 'stop' || r.role === 'now' ? ' · ' : ''}${r.r >= 0 ? '+' : ''}${r.r.toFixed(1)}R` : ''}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function HeldCard({ ctx, held, folded = false, onFold }: {
  ctx: StockReadContextValue;
  held: StockHeld;
  /** One line while Level 2 needs the room (the plan box's own fold). */
  folded?: boolean;
  onFold?: () => void;
}) {
  const who = ctx.who;
  const view = who.view;
  const listening = useOrderTicketListening(ctx.symbol);
  const trade = view?.trade ?? null;
  const novaExit = trade && trade.kind === 'exit' && trade.state === 'holding' && trade.exits === 'nova' ? trade : null;
  const next = rowOf(held, 'next');
  const then = rowOf(held, 'then');
  const stop = held.stop;
  const bid = ctx.topOfBook?.bid ?? null;
  const live = (view?.venue ?? null) === 'live';
  const exitLock = view?.locks.sell ? (live ? HELD_LIVE_EXIT_WHY : view.locks.sell) : null;
  const sellLock = !listening ? 'This tab has no order ticket open to fill. Show the Order Entry module on the rail.'
    : bid === null ? 'No bid on Level 2 yet.' : null;
  const atStop = stop ? (stop.price - held.avg) * held.qty : null;
  const badge = held.raise ? `BROKE $${held.raise.round.toFixed(2)}`
    : stop?.printed ? `STOP ${fmtPx(stop.price)} HIT` : novaExit ? 'NOVA HOLDS THE EXIT' : 'IN THE TRADE';
  const badgeCls = held.raise ? 'broke' : stop?.printed ? 'stophit' : 'held';
  return (
    <section className="sr-plan sr-plan--held" data-testid="held-card" aria-label="The trade you hold">
      <header className="sr-plan__head">
        {onFold && (
          <button type="button" className="sr-plan__fold" aria-expanded={!folded} onClick={onFold}
            {...tipProps(folded ? 'Open the whole trade box' : 'Fold the trade box to one line')} data-testid="held-fold">
            {folded ? '▸' : '▾'}
          </button>
        )}
        <span className="sr-plan__kicker">This trade</span>
        <span className="sr-plan__name">{held.qty.toLocaleString('en-US')} {ctx.symbol} @ {fmtPx(held.avg)}</span>
        <span className={`sr-plan__badge sr-plan__badge--${badgeCls}`} data-testid="held-badge">{badge}</span>
        <span className="sr-plan__rr" {...tipProps(held.risk !== null
          ? `Open P&L, and in R: your ${fmtPx(held.risk)} risk a share.` : 'Open P&L. R is not known: no stop under your average.')}>
          <b className={held.open_usd !== null && held.open_usd < 0 ? 'sr-neg' : ''}>{fmtPnl(held.open_usd)}</b>
          {held.r !== null && <span className="sr-plan__rr-k"> {held.r >= 0 ? '+' : ''}{held.r.toFixed(1)}R open</span>}
        </span>
      </header>
      {folded ? null : (<>
      <div className="sr-plan__nums">
        <div className="sr-num sr-num--entry">
          <span className="sr-num__k">Average</span>
          <span className="sr-num__v">{fmtPx(held.avg)}</span>
          <span className="sr-num__s">{held.qty.toLocaleString('en-US')} shares</span>
        </div>
        <div className="sr-num sr-num--stop" {...tipProps(stop ? `${stopWords(stop)}: ${stop.rule}` : 'No stop yet.', 'Stop')}>
          <span className="sr-num__k">Stop{stop?.source === 'proposed' ? ' · proposed' : ''}</span>
          {novaExit ? (
            <span className="sr-num__v" data-testid="held-stop">{fmtPx(stop?.price ?? novaExit.stop)}</span>
          ) : (
            <PriceInput value={stop?.price ?? null} label="Your stop" testId="held-stop-input"
              onCommit={v => ctx.held.setStop(v)} />
          )}
          <span className="sr-num__s">{stop ? stop.rule : 'type one'}</span>
        </div>
        <div className="sr-num sr-num--target">
          <span className="sr-num__k">Next</span>
          <span className="sr-num__v">{next ? fmtPx(next.price) : '—'}</span>
          <span className="sr-num__s">{next ? next.text : 'no level above'}{then ? ` · then ${fmtPx(then.price)}` : ''}</span>
        </div>
        <div className="sr-num sr-num--risk">
          <span className="sr-num__k">At the stop</span>
          <span className="sr-num__v">{fmtPnl(atStop)}</span>
          <span className="sr-num__s">{atStop !== null && atStop >= 0 ? 'locked in' : 'your risk'}</span>
        </div>
        <div className="sr-num sr-num--size">
          <span className="sr-num__k">Target 2R</span>
          <span className="sr-num__v">{held.target ? fmtPx(held.target.price) : '—'}</span>
          <span className="sr-num__s">{held.target?.traded_at ? 'traded: you are past it' : held.target?.rule ?? 'R not known'}</span>
        </div>
      </div>
      <HeldRuler held={held} />
      <HeldLadder held={held} />
      <LevelRowList levels={held.levels} />
      <CheckList checks={held.checks} />
      <footer className="sr-plan__foot">
        {novaExit ? (
          <>
            <span className="sr-plan__status sr-plan__status--done" data-testid="held-nova-status">
              Nova holds the exit · stop {fmtPx(novaExit.stop)}{novaExit.trail ? ' · raised as levels break' : ''}
            </span>
            <button type="button" className="sr-btn" disabled={who.busy !== null} {...whyProps(who.busy !== null, who.busy)}
              onClick={() => void who.takeOver()} data-testid="held-take-back">Take it back</button>
          </>
        ) : (
          <>
            {stop?.source === 'proposed' && (
              <button type="button" className="sr-btn sr-btn--primary" onClick={() => ctx.held.setStop(stop.price)}
                {...tipProps(`Makes ${fmtPx(stop.price)} your stop for this trade. It places nothing.`)}
                data-testid="held-use-stop">Use stop {fmtPx(stop.price)}</button>
            )}
            {held.raise && (
              <button type="button" className="sr-btn sr-btn--good" onClick={() => ctx.held.setStop(held.raise!.to)}
                {...tipProps(`${held.raise.text}. Your stop for this trade; it places nothing.`)}
                data-testid="held-raise">Raise stop to {fmtPx(held.raise.to)}</button>
            )}
            <button type="button" className="sr-btn" disabled={sellLock !== null} {...whyProps(sellLock !== null, sellLock)}
              {...(sellLock === null ? tipProps('Fills this tab\'s ticket with a sell limit at the bid. It never sends.') : {})}
              onClick={() => bid !== null && requestOrderTicketPrefill({ symbol: ctx.symbol, side: 'SELL', orderType: 'LMT',
                quantityValue: String(held.qty), limitPrice: fmtPx(bid) })}
              data-testid="held-stage-sell">Stage sell {held.qty.toLocaleString('en-US')}</button>
            <button type="button" className="sr-btn sr-btn--nova" disabled={exitLock !== null}
              {...whyProps(exitLock !== null, exitLock)}
              {...(exitLock === null ? tipProps('Hand Nova the sell: a resting stop, raised as round numbers break.') : {})}
              onClick={() => ctx.exitSheet.setOpen(true)} data-testid="held-nova-exit">Nova takes the exit ›</button>
          </>
        )}
        <span className="sr-plan__note">
          {novaExit ? 'Nova\'s stop rests at the broker' : 'your stop and target: no order is working'}
        </span>
      </footer>
      </>)}
      {ctx.exitSheet.open && !novaExit && <ExitSheet ctx={ctx} held={held} lock={exitLock} />}
    </section>
  );
}
