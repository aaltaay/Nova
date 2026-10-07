/**
 * The plan box while you hold the stock (ADR 036 amendment 2026-10-01; operator on mockup v4b: keep the
 * plan box, "i like that bar ... but i also really like the 'then' 'next' 'now' 'broke'"). The same box --
 * header, five numbers, ruler, level rows, checks, buttons -- about your position and measured from the
 * price, with the ladder under the ruler. Its stop is yours to set (never an order); "Nova takes the exit"
 * hands Nova the sell (Paper and Sim; `ExitSheet`).
 *
 * A short (ADR 048) is the mirror: Shorted at, Buy stop, Next (under the price), At the stop and Cover 2R; a
 * round a 1-minute candle closed under offers "Lower stop to X"; Stage cover fills a buy at the ask, and "Nova
 * takes the cover" hands Nova a buy stop that only moves down. The stop order resting at the broker is the
 * card's stop until you set one for the tab.
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
import { HELD_LIVE_COVER_WHY, HELD_LIVE_EXIT_WHY } from './whoTradesModel';
import './heldTrade.css';
import './shortRead.css';

/** The card's words for a long and, mirrored, for a short (ADR 048). */
const LONG_WORDS = {
  avg: 'Average', stop: 'Stop', yourStop: 'Your stop', stopWord: 'stop', target: 'Target 2R', noNext: 'no level above',
  noR: 'no stop under your average', stopHit: 'STOP', novaHolds: 'NOVA HOLDS THE EXIT',
  novaStatus: 'Nova holds the exit · stop', trail: ' · raised as levels break', stage: 'Stage sell',
  stageTip: 'Fills this tab\'s ticket with a sell limit at the bid. It never sends.', novaTakes: 'Nova takes the exit',
  novaTip: 'Hand Nova the sell: a resting stop, raised as round numbers break.',
  novaRests: 'Nova\'s stop rests at the broker', noOrder: 'your stop and target: no order is working',
};
const SHORT_WORDS: typeof LONG_WORDS = {
  avg: 'Shorted at', stop: 'Buy stop', yourStop: 'Your buy stop', stopWord: 'buy stop', target: 'Cover 2R',
  noNext: 'no level below', noR: 'no buy stop over your average', stopHit: 'STOP ↑', novaHolds: 'NOVA HOLDS THE COVER',
  novaStatus: 'Nova holds the cover · buy stop', trail: ' · lowered as levels break', stage: 'Stage cover',
  stageTip: 'Fills this tab\'s ticket with a buy limit at the ask: the cover. It never sends.',
  novaTakes: 'Nova takes the cover',
  novaTip: 'Hand Nova the cover: a resting buy stop, lowered as round numbers break. Paper and Sim only.',
  novaRests: 'Nova\'s buy stop rests at the broker', noOrder: 'your buy stop and cover: no order is working',
};

const SHORT_TAG_TIP = 'You hold it short: borrowed through IBKR and sold. You make money as it falls; the buy stop '
  + 'over the price is your risk. Nova covers what is left at 15:55 ET.';

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
  const short = held.side === 'short';
  const w = short ? SHORT_WORDS : LONG_WORDS;
  const next = rowOf(held, 'next');
  const then = rowOf(held, 'then');
  const stop = held.stop;
  // The stop's move a candle's close offers: a long's raise, a short's lower.
  const move = short ? held.lower ?? null : held.raise;
  // A long sells at the bid; a short covers with a buy at the ask.
  const quote = short ? ctx.topOfBook?.ask ?? null : ctx.topOfBook?.bid ?? null;
  const live = (view?.venue ?? null) === 'live';
  const exitLock = view?.locks.sell ? (live ? (short ? HELD_LIVE_COVER_WHY : HELD_LIVE_EXIT_WHY) : view.locks.sell) : null;
  const sellLock = !listening ? 'This tab has no order ticket open to fill. Show the Order Entry module on the rail.'
    : quote === null ? `No ${short ? 'ask' : 'bid'} on Level 2 yet.` : null;
  const atStop = stop ? (short ? held.avg - stop.price : stop.price - held.avg) * held.qty : null;
  const resting = !novaExit && stop && stop.source === 'yours' && ctx.held.track.stop === null
    && ctx.position?.workingStop != null && Math.abs(ctx.position.workingStop - stop.price) < 1e-6;
  const badge = move ? `BROKE $${move.round.toFixed(2)}`
    : stop?.printed ? `${w.stopHit} ${fmtPx(stop.price)} HIT` : novaExit ? w.novaHolds : 'IN THE TRADE';
  const badgeCls = move ? 'broke' : stop?.printed ? 'stophit' : 'held';
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
        {short && <span className="sr-plan__side" {...tipProps(SHORT_TAG_TIP, 'Short')} data-testid="held-short-tag">SHORT</span>}
        <span className="sr-plan__name">{held.qty.toLocaleString('en-US')} {ctx.symbol} @ {fmtPx(held.avg)}</span>
        <span className={`sr-plan__badge sr-plan__badge--${badgeCls}`} data-testid="held-badge">{badge}</span>
        <span className="sr-plan__rr" {...tipProps(held.risk !== null
          ? `Open P&L, and in R: your ${fmtPx(held.risk)} risk a share.` : `Open P&L. R is not known: ${w.noR}.`)}>
          <b className={held.open_usd !== null && held.open_usd < 0 ? 'sr-neg' : ''}>{fmtPnl(held.open_usd)}</b>
          {held.r !== null && <span className="sr-plan__rr-k"> {held.r >= 0 ? '+' : ''}{held.r.toFixed(1)}R open</span>}
        </span>
      </header>
      {folded ? null : (<>
      <div className="sr-plan__nums">
        <div className="sr-num sr-num--entry">
          <span className="sr-num__k">{w.avg}</span>
          <span className="sr-num__v">{fmtPx(held.avg)}</span>
          <span className="sr-num__s">{held.qty.toLocaleString('en-US')} shares{short ? ' short' : ''}</span>
        </div>
        <div className="sr-num sr-num--stop" {...tipProps(stop ? `${stopWords(stop)}: ${stop.rule}` : 'No stop yet.', w.stop)}>
          <span className="sr-num__k">{w.stop}{stop?.source === 'proposed' ? ' · proposed' : ''}</span>
          {novaExit ? (
            <span className="sr-num__v" data-testid="held-stop">{fmtPx(stop?.price ?? novaExit.stop)}</span>
          ) : (
            <PriceInput value={stop?.price ?? null} label={w.yourStop} testId="held-stop-input"
              onCommit={v => ctx.held.setStop(v)} />
          )}
          <span className="sr-num__s">{resting ? 'resting at the broker' : stop ? stop.rule : 'type one'}</span>
        </div>
        <div className="sr-num sr-num--target">
          <span className="sr-num__k">Next</span>
          <span className="sr-num__v">{next ? fmtPx(next.price) : '—'}</span>
          <span className="sr-num__s">{next ? next.text : w.noNext}{then ? ` · then ${fmtPx(then.price)}` : ''}</span>
        </div>
        <div className="sr-num sr-num--risk">
          <span className="sr-num__k">At the stop</span>
          <span className="sr-num__v">{fmtPnl(atStop)}</span>
          <span className="sr-num__s">{atStop !== null && atStop >= 0 ? 'locked in' : 'your risk'}</span>
        </div>
        <div className="sr-num sr-num--size">
          <span className="sr-num__k">{w.target}</span>
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
              {w.novaStatus} {fmtPx(novaExit.stop)}{novaExit.trail ? w.trail : ''}
            </span>
            <button type="button" className="sr-btn" disabled={who.busy !== null} {...whyProps(who.busy !== null, who.busy)}
              onClick={() => void who.takeOver()} data-testid="held-take-back">Take it back</button>
          </>
        ) : (
          <>
            {stop?.source === 'proposed' && (
              <button type="button" className="sr-btn sr-btn--primary" onClick={() => ctx.held.setStop(stop.price)}
                {...tipProps(`Makes ${fmtPx(stop.price)} your ${w.stopWord} for this trade. It places nothing.`)}
                data-testid="held-use-stop">Use stop {fmtPx(stop.price)}</button>
            )}
            {move && (
              <button type="button" className="sr-btn sr-btn--good" onClick={() => ctx.held.setStop(move.to)}
                {...tipProps(`${move.text}. Your ${w.stopWord} for this trade; it places nothing.`)}
                data-testid={short ? 'held-lower' : 'held-raise'}>{short ? 'Lower' : 'Raise'} stop to {fmtPx(move.to)}</button>
            )}
            <button type="button" className="sr-btn" disabled={sellLock !== null} {...whyProps(sellLock !== null, sellLock)}
              {...(sellLock === null ? tipProps(w.stageTip) : {})}
              onClick={() => quote !== null && requestOrderTicketPrefill({ symbol: ctx.symbol, side: short ? 'BUY' : 'SELL',
                orderType: 'LMT', quantityValue: String(held.qty), limitPrice: fmtPx(quote) })}
              data-testid={short ? 'held-stage-cover' : 'held-stage-sell'}>{w.stage} {held.qty.toLocaleString('en-US')}</button>
            <button type="button" className="sr-btn sr-btn--nova" disabled={exitLock !== null}
              {...whyProps(exitLock !== null, exitLock)}
              {...(exitLock === null ? tipProps(w.novaTip) : {})}
              onClick={() => ctx.exitSheet.setOpen(true)} data-testid="held-nova-exit">{w.novaTakes} ›</button>
          </>
        )}
        <span className="sr-plan__note" data-testid="held-note">
          {novaExit ? w.novaRests : resting ? `your ${w.stopWord} ${fmtPx(stop!.price)} is working at the broker`
            : w.noOrder}
        </span>
      </footer>
      </>)}
      {ctx.exitSheet.open && !novaExit && <ExitSheet ctx={ctx} held={held} lock={exitLock} />}
    </section>
  );
}
