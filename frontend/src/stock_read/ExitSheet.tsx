/**
 * "Nova takes the exit" (ADR 037 amendment 2026-10-01): the sheet over the plan box that hands Nova the
 * sell of the shares you bought -- a resting SELL stop, raised as 1-minute candles close over round
 * numbers. Paper, and Sim at the live edge; on Live it is locked and says why. The target and the flush
 * sell are shown, locked, with why they are not Nova's yet.
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

export function ExitSheet({ ctx, held, lock }: { ctx: StockReadContextValue; held: StockHeld; lock: string | null }) {
  const start = held.raise?.to ?? held.stop?.price ?? null;
  const [stop, setStop] = useState<number | null>(start);
  const [trail, setTrail] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const last = held.price;
  const bad = stop === null ? 'Type a stop under the price.'
    : last !== null && stop >= last ? `The stop ${fmtPx(stop)} is at or over the price ${fmtPx(last)}: it would sell at once.`
      : null;
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
    <div className="sr-exit" role="dialog" aria-label={`Nova takes the exit on ${held.qty} ${ctx.symbol}`} data-testid="exit-sheet">
      <h3 className="sr-exit__title">Nova takes the exit on {held.qty.toLocaleString('en-US')} {ctx.symbol}</h3>
      <p className="sr-exit__sub">
        You bought these. Nova places and manages the sell on {ctx.who.view?.venue === 'sim' ? 'Sim' : 'Paper'}; take it
        back at any moment.
      </p>
      {lock && <p className="sr-exit__lock" data-testid="exit-lock">{lock}</p>}
      <div className="sr-exit__opt">
        <span className="sr-exit__k">Stop</span>
        <PriceInput value={stop} label="Nova's stop" testId="exit-stop" onCommit={v => setStop(v)} />
        <span className="sr-exit__s">
          {held.raise ? held.raise.text : held.stop ? held.stop.rule : 'under the price'} · a SELL stop for every share
        </span>
      </div>
      <label className="sr-exit__opt sr-exit__check">
        <input type="checkbox" checked={trail} onChange={e => setTrail(e.target.checked)} data-testid="exit-trail" />
        <span>Raise the stop as levels break
          <small>Under each half / whole dollar a 1-minute candle closes over (5c under a half dollar). Up only, never
            down; each raise is a line in the audit and a ping.</small>
        </span>
      </label>
      <div className="sr-exit__opt sr-exit__opt--locked" aria-disabled="true" {...whyProps(true, EXIT_TARGET_WHY)} data-testid="exit-target">
        <span className="sr-exit__k">Target</span>
        <span className="sr-exit__s">{EXIT_TARGET_WHY}</span>
      </div>
      <div className="sr-exit__opt sr-exit__opt--locked" aria-disabled="true" {...whyProps(true, EXIT_FLUSH_WHY)} data-testid="exit-flush">
        <span className="sr-exit__k">Flush</span>
        <span className="sr-exit__s">Sell on a 30 s flush · {EXIT_FLUSH_WHY}</span>
      </div>
      <p className="sr-exit__sends" data-testid="exit-sends">
        <b>Nova sends:</b> SELL {held.qty.toLocaleString('en-US')} {ctx.symbol} STP {fmtPx(stop)}
        {trail ? ', replaced at each broken level' : ''}. Nothing else.
      </p>
      {error && <p className="sr-exit__error" data-testid="exit-error">{error}</p>}
      <div className="sr-exit__foot">
        <button type="button" className="sr-btn sr-btn--nova" disabled={why !== null} {...whyProps(why !== null, why)}
          {...(why === null ? tipProps(`Places a SELL stop at ${fmtPx(stop)} for ${held.qty} shares.`) : {})}
          onClick={() => void send()} data-testid="exit-send">Nova takes the exit</button>
        <button type="button" className="sr-btn" onClick={() => ctx.exitSheet.setOpen(false)} data-testid="exit-cancel">
          Cancel
        </button>
      </div>
    </div>
  );
}
