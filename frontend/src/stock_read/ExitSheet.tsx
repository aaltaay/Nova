/**
 * "Nova takes the exit" (ADR 037 amendment 2026-10-01): the sheet over the plan box that hands Nova the
 * sell of the shares you bought -- a resting SELL stop, raised as 1-minute candles close over round
 * numbers. Paper, and Sim; on Live it is locked and says why.
 *
 * Targets beside the stop (#681, ADR 037 amendment 2026-10-12): target 1 sells the first half, target 2 the
 * rest, as one exit pair with the stop -- a target's fill shrinks the stop to the shares left, and the stop
 * stays where it is. They start from the read's targets (#845) still ahead of the price -- one the price
 * already passed gives its place to the next, which then sells every share; empty, the stop goes alone. The flush sell is shown, locked, with why it is not Nova's yet.
 *
 * A short you hold (ADR 048) gets "Nova takes the cover", the mirror: a resting BUY stop over the price,
 * lowered as candles close under round numbers, never raised, and its cover targets under the price. No
 * flush cover: trial T1 reads a long's tape.
 */
import { useState } from 'react';
import { tipProps, whyProps } from '../ux';
import { limitWords, splitHalves, startTargets, targetProblem } from './exitTargets';
import type { StockHeld } from './heldRead';
import { PriceInput } from './PlanNumbers';
import { fmtPx } from './planMath';
import type { StockReadContextValue } from './StockReadContext';

export const EXIT_FLUSH_WHY = 'Not one of Nova\'s exits: trial T1 has not read. The chart still calls SELL NOW · FLUSH '
  + '(in trial).';
export const EXIT_TARGETS_HOW = 'One exit pair with the stop: a target\'s fill shrinks the stop to the shares left, '
  + 'and the stop stays where it is. Empty: the stop alone.';

export function ExitSheet({ ctx, held, lock }: { ctx: StockReadContextValue; held: StockHeld; lock: string | null }) {
  const short = held.side === 'short';
  const move = short ? held.lower ?? null : held.raise;
  const start = move?.to ?? held.stop?.price ?? null;
  const last = held.price;
  const [stop, setStop] = useState<number | null>(start);
  const [target1, setTarget1] = useState<number | null>(
    () => startTargets(short, held.target?.price, held.target2?.price, last)[0]);
  const [target2, setTarget2] = useState<number | null>(
    () => startTargets(short, held.target?.price, held.target2?.price, last)[1]);
  const [trail, setTrail] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const fraction = held.target1_fraction ?? null;
  const [first, second] = splitHalves(held.qty, target1, target2, fraction, short);
  const bad = stop === null ? (short ? 'Type a buy stop over the price.' : 'Type a stop under the price.')
    : last !== null && !short && stop >= last
      ? `The stop ${fmtPx(stop)} is at or over the price ${fmtPx(last)}: it would sell at once.`
      : last !== null && short && stop <= last
        ? `The buy stop ${fmtPx(stop)} is at or under the price ${fmtPx(last)}: it would cover at once.`
        : targetProblem(short, last, stop, target1, target2);
  const takes = short ? 'Nova takes the cover' : 'Nova takes the exit';
  const venueName = ctx.who.view?.venue === 'sim' ? 'Sim' : 'Paper';
  const why = lock ?? bad ?? (sending ? 'Sending…' : null);
  const side = short ? 'BUY' : 'SELL';
  const send = async () => {
    if (why !== null || stop === null) return;
    setSending(true);
    setError(null);
    try {
      await ctx.who.takeExit(stop, trail, target1 === null ? null : {
        target: target1, target2: second ? target2 : null, target1_fraction: second ? fraction ?? 0.5 : null,
      });
      ctx.exitSheet.setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  };
  const aims = target1 === null ? ''
    : `; ${limitWords(held.qty, target1, target2, fraction, short)}`
      + ' beside it, one-cancels-other (a target\'s fill shrinks the stop to the shares left)';
  return (
    <div className="sr-exit" role="dialog" aria-label={`${takes} on ${held.qty} ${ctx.symbol}`} data-testid="exit-sheet">
      <h3 className="sr-exit__title">{takes} on {held.qty.toLocaleString('en-US')} {ctx.symbol}{short ? ' short' : ''}</h3>
      <p className="sr-exit__sub">
        {short ? `You shorted these. Nova places and manages the cover on ${venueName}`
          : `You bought these. Nova places and manages the sell on ${venueName}`}; take it back at any moment.
      </p>
      {lock && <p className="sr-exit__lock" data-testid="exit-lock">{lock}</p>}
      <div className="sr-exit__opt">
        <span className="sr-exit__k">{short ? 'Buy stop' : 'Stop'}</span>
        <PriceInput value={stop} label={short ? 'Nova\'s buy stop' : 'Nova\'s stop'} testId="exit-stop"
          onCommit={v => setStop(v)} />
        <span className="sr-exit__s">
          {move ? move.text : held.stop ? held.stop.rule : short ? 'over the price' : 'under the price'}
          {short ? ' · a BUY stop for every share' : ' · a SELL stop for every share'}
        </span>
      </div>
      <label className="sr-exit__opt sr-exit__check">
        <input type="checkbox" checked={trail} onChange={e => setTrail(e.target.checked)} data-testid="exit-trail" />
        {short ? (
          <span>Lower the stop as levels break
            <small>Over each round number a 1-minute candle closes under (5c over a half dollar). Down only, never up;
              each lower is a line in the audit and a ping.</small>
          </span>
        ) : (
          <span>Raise the stop as levels break
            <small>Under each half / whole dollar a 1-minute candle closes over (5c under a half dollar). Up only, never
              down; each raise is a line in the audit and a ping.</small>
          </span>
        )}
      </label>
      <div className="sr-exit__opt" {...tipProps(EXIT_TARGETS_HOW)} data-testid="exit-target">
        <span className="sr-exit__k">Target 1</span>
        <PriceInput value={target1} label={short ? 'Nova\'s cover target 1' : 'Nova\'s target 1'} testId="exit-target1"
          onCommit={v => setTarget1(v)} />
        <span className="sr-exit__s">
          {target1 === null ? `${short ? 'Under' : 'Over'} the price · empty: the stop alone`
            : second ? `the first half, ${first} shares` : `every share, ${first}`}
          {held.target && target1 === held.target.price && held.target.rule ? ` · ${held.target.rule}` : ''}
        </span>
      </div>
      <div className="sr-exit__opt" data-testid="exit-target2-row">
        <span className="sr-exit__k">Target 2</span>
        <PriceInput value={target2} label={short ? 'Nova\'s cover target 2' : 'Nova\'s target 2'} testId="exit-target2"
          onCommit={v => setTarget2(v)} />
        <span className="sr-exit__s">
          {second ? `the rest, ${second} shares; the stop stays where it is after the first half`
            : held.qty < 2 ? 'one share sells whole at target 1' : 'empty: every share at target 1'}
          {held.target2 && target2 === held.target2.price && held.target2.rule ? ` · ${held.target2.rule}` : ''}
        </span>
      </div>
      {!short && (
        <div className="sr-exit__opt sr-exit__opt--locked" aria-disabled="true" {...whyProps(true, EXIT_FLUSH_WHY)} data-testid="exit-flush">
          <span className="sr-exit__k">Flush</span>
          <span className="sr-exit__s">Sell on a 30 s flush · {EXIT_FLUSH_WHY}</span>
        </div>
      )}
      <p className="sr-exit__sends" data-testid="exit-sends">
        <b>Nova sends:</b> {side} {held.qty.toLocaleString('en-US')} {ctx.symbol} STP {fmtPx(stop)}
        {trail ? ', replaced at each broken level' : ''}{aims}. Nothing else.
      </p>
      {error && <p className="sr-exit__error" data-testid="exit-error">{error}</p>}
      <div className="sr-exit__foot">
        <button type="button" className="sr-btn sr-btn--nova" disabled={why !== null} {...whyProps(why !== null, why)}
          {...(why === null ? tipProps(`Places a ${side} stop at ${fmtPx(stop)} for ${held.qty} shares`
            + `${target1 !== null ? ' and its targets beside it' : ''}.`) : {})}
          onClick={() => void send()} data-testid="exit-send">{takes}</button>
        <button type="button" className="sr-btn" onClick={() => ctx.exitSheet.setOpen(false)} data-testid="exit-cancel">
          Cancel
        </button>
      </div>
    </div>
  );
}
