/**
 * Who trades it, per ticker and for all at once (operator ask 2026-10-12): the You | Bot switch of one row, and the
 * switch for all on the hot list's group row. The switch for all sets Entry (or Exit) on every ticker in that group,
 * one by one through the row's own door (`PUT /api/stock-mode/{symbol}`), biggest change first, so every refusal a
 * row has -- the Live lock, a stock you hold, a full bot list -- still refuses it, and is said with its tickers.
 * A ticker that joins the hot list later comes in at You, as every new one does.
 */
import { useCallback, useState } from 'react';
import { putStockMode } from '../stock_read';
import { tipProps, whyProps } from '../ux';
import type { StockModeRow } from './stockModesApi';
import { allSidesPairs, commonSide, refusalLines, sidesOf, WHO_WORDS, type Side } from './tickerTable';

export function SideSeg({ label, name = label, value, onPick, lock }: {
  label: string;
  /** The radiogroup's name, when it differs from the label it shows. */
  name?: string;
  /** null: neither lit (the rows differ). */
  value: Side | null;
  onPick: (s: Side) => void;
  lock: string | null;
}) {
  return (
    <span className="bots-tk__side"><span className="bots-tk__side-label">{label}</span>
      <span className="bots-mini-seg" role="radiogroup" aria-label={name}>
        {(['you', 'nova'] as const).map(s => (
          <button key={s} type="button" role="radio" aria-checked={value === s} disabled={lock !== null}
            {...(lock ? whyProps(true, lock) : {})} onClick={() => { if (value !== s) onPick(s); }}>{s === 'you' ? 'You' : 'Bot'}</button>
        ))}
      </span>
    </span>
  );
}

/** The switch for all's run: what it is setting now (the lock on every switch of the table), and what refused. */
export function useAllSides(modes: readonly StockModeRow[], onModesChanged: () => void) {
  const [busy, setBusy] = useState<string | null>(null);
  const [refused, setRefused] = useState<string[]>([]);
  const setAll = useCallback(async (symbols: readonly string[], which: 'entry' | 'exit', to: Side) => {
    const pairs = allSidesPairs(symbols, modes, which, to);
    if (!pairs.length) return;
    setRefused([]);
    const out: { symbol: string; text: string }[] = [];
    for (const [i, p] of pairs.entries()) {
      setBusy(`Setting ${which === 'entry' ? 'Entry' : 'Exit'} to ${to === 'you' ? 'You' : 'Bot'}: ${p.symbol}, ${i + 1} of ${pairs.length}…`);
      try {
        await putStockMode(p.symbol, p.buy, p.sell);
      } catch (err) {
        out.push({ symbol: p.symbol, text: err instanceof Error ? err.message : String(err) });
      }
    }
    setBusy(null);
    setRefused(refusalLines(out));
    onModesChanged();
  }, [modes, onModesChanged]);
  return { busy, refused, setAll };
}

export function AllSides({ symbols, modes, busy, onSet }: {
  symbols: readonly string[];
  modes: readonly StockModeRow[];
  busy: string | null;
  onSet: (which: 'entry' | 'exit', to: Side) => void;
}) {
  const sides = symbols.map(s => sidesOf(s, modes));
  const entry = commonSide(sides.map(([buy]) => buy));
  const exit = commonSide(sides.map(([, sell]) => sell));
  const tip = `Sets Entry (or Exit) on all ${symbols.length} tickers in this group, one by one, as each row's own `
    + 'switch would; a ticker that refuses keeps its side and says why. Unlit: the tickers differ. A ticker that '
    + 'joins the hot list later comes in at You.';
  return (
    <span className="bots-tk__all" data-testid="bots-tk-all">
      <span className="bots-tk__all-label" {...tipProps(tip, 'Who trades it, for all')}>All {symbols.length}</span>
      <SideSeg label="Entry" name="Entry for all" value={entry} lock={busy} onPick={s => onSet('entry', s)} />
      <SideSeg label="Exit" name="Exit for all" value={exit} lock={busy} onPick={s => onSet('exit', s)} />
      {entry && exit ? <span className={`bots-tk__who bots-tk__who--${entry}-${exit}`}>{WHO_WORDS[`${entry}/${exit}`]}</span>
        : <span className="bots-tk__who">mixed</span>}
    </span>
  );
}
