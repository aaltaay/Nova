/**
 * IBKR's three Level 2 lines on one row (ADR 043): who holds each (your Trader tab, in front or hidden, a
 * Record, auto-record, a loan), the switch that lets a hidden tab lend its line to a setup near its trigger
 * on a stock Nova buys, and the loans now and today. Read every few seconds while the page shows.
 */
import { useCallback, useEffect, useState } from 'react';
import { tipProps, whyProps } from '../ux';
import { etTime } from './botWhen';
import { fetchLines, setLending, type DepthLine, type LinesView } from './linesApi';

const LINES_POLL_MS = 5_000;
const HELD: Record<string, string> = {
  tab: 'your Trader tab', record: 'your Record', auto_record: 'auto-record', loan: 'lent to a setup', replay: 'the Sim replay',
};

function holder(l: DepthLine): string {
  if (l.heldBy === 'tab') return `${HELD.tab} · ${l.front === true ? 'in front' : l.front === false ? 'hidden' : 'not known if in front'}`;
  return HELD[l.heldBy] ?? l.heldBy;
}

export function BotLinesCard() {
  const [view, setView] = useState<LinesView | null>(null);
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
        <span className="bots-card__sub">IBKR gives {cap}. Nova reads the tape only where it holds one.</span>
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
          {...(lock ? whyProps(true, lock) : tipProps('When a setup of a strategy at On, on a stock whose Buy is Nova, is armed, near its trigger or in a trade and no line is free, a Trader tab you are not looking at lends it its line. It comes back when the setup ends, the trade ends or you bring that tab to the front. The tab in front never lends.', 'Hidden tabs lend their line'))}
          onClick={() => void toggle()} data-testid="bots-lines-lending">
          <span className="bots-switch__track" aria-hidden="true" />
          <span className="bots-switch__txt"><b>Hidden tabs lend their line</b>
            <small>to a setup near its trigger on a stock Nova buys; back when it ends or you bring the tab to the front</small></span>
        </button>
        <div className="bots-lines__loans" data-testid="bots-lines-loans">
          {lending?.loans.length ? lending.loans.map(l => (
            <span key={`${l.lender}-${l.borrower}`}>Now: <b>{l.lender}</b>'s line is lent to <b>{l.borrower}</b>{l.setupType ? ` (${l.setupType.replace(/_/g, ' ')})` : ''}{l.since ? ` since ${etTime(l.since)}` : ''}.</span>
          )) : <span>No line is lent now.</span>}
          {lending?.recent.slice(0, 3).map(l => (
            <span key={`${l.lender}-${l.borrower}-${l.since}`} className="bots-muted">
              {l.since ? etTime(l.since) : '?'}–{l.ended ? etTime(l.ended) : '?'} {l.lender} → {l.borrower}{l.end ? ` (${l.end.replace(/_/g, ' ')})` : ''}
            </span>
          ))}
          {error ? <span className="is-bad">{error}</span> : null}
        </div>
      </div>
    </section>
  );
}
