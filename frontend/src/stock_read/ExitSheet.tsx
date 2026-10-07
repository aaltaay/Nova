/**
 * "Nova takes the exit" (ADR 037 amendment 2026-10-01): the sheet over the plan box that hands Nova the
 * sell of the shares you bought -- a resting SELL stop, raised as 1-minute candles close over round
 * numbers. Paper, and Sim at the live edge; on Live it is locked and says why. The target and the flush
 * sell are shown, locked, with why they are not Nova's yet.
 *
 * A short you hold (ADR 048) gets "Nova takes the cover", the mirror: a resting BUY stop over the price,
 * lowered as candles close under round numbers, never raised. No flush cover: trial T1 reads a long's tape.
 */
import { useState } from 'react';
import { tipProps, whyProps } from '../ux';
import type { StockHeld } from './heldRead';
import { PriceInput } from './PlanNumbers';
import { fmtPx } from './planMath';
import type { StockReadContextValue } from './StockReadContext';

export const EXIT_TARGET_WHY = 'Not yet: Nova\'s execution door lets one order sell the same shares, and a stop with a '
  + 'target beside it needs a one-cancels-other exit pair (#681). Let the stop take it, raised as levels break.';
export const EXIT_FLUSH_WHY = 'Not one of Nova\'s exits: trial T1 has not read. The chart still calls SELL NOW · FLUSH '
  + '(in trial).';
export const COVER_TARGET_WHY = 'Not yet: a buy stop with a cover target beside it needs a one-cancels-other exit pair '
  + '(#681). Let the stop take it, lowered as levels break.';

export function ExitSheet({ ctx, held, lock }: { ctx: StockReadContextValue; held: StockHeld; lock: string | null }) {
  const short = held.side === 'short';
  const move = short ? held.lower ?? null : held.raise;
  const start = move?.to ?? held.stop?.price ?? null;
  const [stop, setStop] = useState<number | null>(start);
  const [trail, setTrail] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const last = held.price;
  const bad = stop === null ? (short ? 'Type a buy stop over the price.' : 'Type a stop under the price.')
    : last !== null && !short && stop >= last
      ? `The stop ${fmtPx(stop)} is at or over the price ${fmtPx(last)}: it would sell at once.`
      : last !== null && short && stop <= last
        ? `The buy stop ${fmtPx(stop)} is at or under the price ${fmtPx(last)}: it would cover at once.`
        : null;
  const takes = short ? 'Nova takes the cover' : 'Nova takes the exit';
  const venueName = ctx.who.view?.venue === 'sim' ? 'Sim' : 'Paper';
  const why = lock ?? bad ?? (sending ? 'Sending…' : null);
  const send = async () => {
    if (why !== null || stop === null) return;
    setSending(true);
    setError(null);
    try {
      await ctx.who.takeExit(stop, trail);
      ctx.exitSheet.setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  };
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
      <div className="sr-exit__opt sr-exit__opt--locked" aria-disabled="true"
        {...whyProps(true, short ? COVER_TARGET_WHY : EXIT_TARGET_WHY)} data-testid="exit-target">
        <span className="sr-exit__k">Target</span>
        <span className="sr-exit__s">{short ? COVER_TARGET_WHY : EXIT_TARGET_WHY}</span>
      </div>
      {!short && (
        <div className="sr-exit__opt sr-exit__opt--locked" aria-disabled="true" {...whyProps(true, EXIT_FLUSH_WHY)} data-testid="exit-flush">
          <span className="sr-exit__k">Flush</span>
          <span className="sr-exit__s">Sell on a 30 s flush · {EXIT_FLUSH_WHY}</span>
        </div>
      )}
      <p className="sr-exit__sends" data-testid="exit-sends">
        <b>Nova sends:</b> {short ? 'BUY' : 'SELL'} {held.qty.toLocaleString('en-US')} {ctx.symbol} STP {fmtPx(stop)}
        {trail ? ', replaced at each broken level' : ''}. Nothing else.
      </p>
      {error && <p className="sr-exit__error" data-testid="exit-error">{error}</p>}
      <div className="sr-exit__foot">
        <button type="button" className="sr-btn sr-btn--nova" disabled={why !== null} {...whyProps(why !== null, why)}
          {...(why === null ? tipProps(`Places a ${short ? 'BUY' : 'SELL'} stop at ${fmtPx(stop)} for ${held.qty} shares.`) : {})}
          onClick={() => void send()} data-testid="exit-send">{takes}</button>
        <button type="button" className="sr-btn" onClick={() => ctx.exitSheet.setOpen(false)} data-testid="exit-cancel">
          Cancel
        </button>
      </div>
    </div>
  );
}
