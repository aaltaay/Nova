/**
 * IBKR's three Level 2 lines on one row (ADR 044): who holds each (your Trader tab, in front or hidden, a
 * Record, auto-record, a loan), the switch that lets a hidden tab lend its Level 2 and Time & Sales lines to
 * a setup near its trigger on a stock Nova trades, and the loans now -- with whether the setup's prints arrive
 * -- and today. Read every few seconds while the page shows.
 */
import { useCallback, useEffect, useState } from 'react';
import { tipProps, whyProps } from '../ux';
import { etTime } from './botWhen';
import type { DepthLine, DepthLinesView, DepthLoan } from '../ibkr';
import { fetchLines, setLending } from './linesApi';

const LINES_POLL_MS = 5_000;
const HELD: Record<string, string> = {
  tab: 'your Trader tab', record: 'your Record', auto_record: 'auto-record', loan: 'lent to a setup', replay: 'the Sim replay',
};

function holder(l: DepthLine): string {
  if (l.held_by === 'tab') return `${HELD.tab} · ${l.front === true ? 'in front' : l.front === false ? 'hidden' : 'not known if in front'}`;
  return HELD[l.held_by] ?? l.held_by;
}

const TAPE_WORDS: Record<string, string> = {
  receiving: 'its prints arrive', waiting: 'its Time & Sales line is up, no print yet', refused: 'no Time & Sales line',
};

/** One loan in words: the backend's sentence, then whether the setup's prints arrive (or why not). */
function loanWords(l: DepthLoan): string {
  const base = l.text ?? `${l.lender}'s lines are lent to ${l.borrower}${l.setup_type ? ` (${l.setup_type.replace(/_/g, ' ')})` : ''}`;
  const tape = l.tape_state ? TAPE_WORDS[l.tape_state] : null;
  return `${base}${tape ? ` · ${tape}` : ''}${l.tape_error ? ` (${l.tape_error})` : ''}`;
}

export function BotLinesCard() {
  const [view, setView] = useState<DepthLinesView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      setView(await fetchLines());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);
  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), LINES_POLL_MS);
    return () => clearInterval(t);
  }, [load]);
  const toggle = async () => {
    if (!view) return;
    setBusy(true);
    try {
      setView(await setLending(!view.lending.on));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  const cap = view?.cap ?? 3;
  const slots: (DepthLine | null)[] = [...(view?.lines ?? [])];
  while (slots.length < cap) slots.push(null);
  const lending = view?.lending;
  const lock = busy ? 'Saving…' : view ? null : (error ?? 'Reading who holds the lines…');
  return (
    <section className="bots-card bots-lines" data-testid="bots-lines">
      <div className="bots-lines__head">
        <h3>Level 2 lines <span className="bots-source">{view ? `${view.lines.length} of ${cap}` : '…'}</span></h3>
        <span className="bots-card__sub">IBKR gives {cap}, and as many Time &amp; Sales lines. Nova reads the tape only where it holds both.</span>
      </div>
      <div className="bots-lines__row">
        {slots.map((l, i) => (
          <div key={l?.symbol ?? `free-${i}`} className={`bots-lines__slot${l?.front ? ' is-front' : ''}${l ? '' : ' is-free'}`}
            data-testid={`bots-line-${l?.symbol ?? `free-${i}`}`}>
            <b>{l?.symbol ?? 'free'}</b>
            <small>{l ? holder(l) : 'no line held'}</small>
          </div>
        ))}
        <button type="button" className={`bots-switch bots-switch--small${lending?.on ? ' is-on' : ''}`} role="switch"
          aria-checked={lending?.on === true} disabled={lock !== null}
          {...(lock ? whyProps(true, lock) : tipProps('When a setup of a strategy at On, on a stock whose Buy is Nova, is armed, near its trigger or in a trade and no line is free, a Trader tab you are not looking at lends it its Level 2 and Time & Sales lines. They come back together when the setup ends, the trade ends or you bring that tab to the front. The tab in front never lends.', 'Hidden tabs lend their lines'))}
          onClick={() => void toggle()} data-testid="bots-lines-lending">
          <span className="bots-switch__track" aria-hidden="true" />
          <span className="bots-switch__txt"><b>Hidden tabs lend their lines</b>
            <small>to a setup near its trigger on a stock Nova trades; back when it ends or you bring the tab to the front</small></span>
        </button>
        <div className="bots-lines__loans" data-testid="bots-lines-loans">
          {lending?.loans.length ? lending.loans.map(l => (
            <span key={`${l.lender}-${l.borrower}`} className={l.tape_state === 'refused' ? 'is-bad' : undefined}
              data-testid={`bots-lines-loan-${l.lender}`}>
              Now{l.since ? ` (${etTime(l.since)})` : ''}: {loanWords(l)}
            </span>
          )) : <span>No line is lent now.</span>}
          {lending?.error ? <span className="is-bad">{lending.error}</span> : null}
          {lending?.recent.slice(0, 3).map(l => (
            <span key={`${l.lender}-${l.borrower}-${l.since}`} className="bots-muted">
              {l.since ? etTime(l.since) : '?'}–{l.ended ? etTime(l.ended) : '?'} {l.text ?? `${l.lender} → ${l.borrower}`}{l.end ? ` (${l.end.replace(/_/g, ' ')})` : ''}
            </span>
          ))}
          {error ? <span className="is-bad">{error}</span> : null}
        </div>
      </div>
    </section>
  );
}
