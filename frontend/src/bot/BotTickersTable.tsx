/**
 * Tickers today (ADR 043): today's hot list and the squares, by ticker. Each listed ticker has a "now" row
 * -- would Nova buy it if its setup triggered this minute -- with its Buy / Sell switch, and under it every
 * trigger of the day on it, judged by the same checks; red is what stopped it. Tickers that triggered but
 * are not listed fold at the end. Under the table, what each gate did to the day's triggers.
 */
import { useCallback, useEffect, useState } from 'react';
import { HOT_LIST_AUTO_CHOICES, hotListActions, listedOn, useHotList } from '../hot_list';
import { putStockMode } from '../stock_read';
import { tipProps, whyProps } from '../ux';
import { setupName } from './botsPageFormat';
import { etTime } from './botWhen';
import type { StockModeRow } from './stockModesApi';
import { daySummary, GATE_TIPS, orderTickers, resultWords, sidesOf, splitReasons, WHO_WORDS, type Side } from './tickerTable';
import { fetchTriggers, type Cells, type TickerRow, type TriggersView } from './triggersApi';
import type { SetupRow } from '../setups';

const TRIGGERS_POLL_MS = 15_000;

/** The triggers table, polled while the page shows; a date other than today is read once. */
export function useTriggers(date: string | null, enabled = true): { view: TriggersView | null; error: string | null } {
  const [view, setView] = useState<TriggersView | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled) return undefined;
    let alive = true;
    const read = async () => {
      try {
        const next = await fetchTriggers(date ?? undefined);
        if (alive) { setView(next); setError(null); }
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : String(err));
      }
    };
    void read();
    const t = date ? null : setInterval(() => void read(), TRIGGERS_POLL_MS);
    return () => { alive = false; if (t) clearInterval(t); };
  }, [date, enabled]);
  return { view, error };
}

function Squares({ cells, order }: { cells: Cells; order: readonly string[] }) {
  return <>{order.map(id => {
    const c = cells[id];
    const ok = c ? c.ok : null;
    return (
      <td key={id} className="bots-tk__g">
        <span className={`bots-tk__cell ${ok === null ? 'is-na' : ok ? 'is-ok' : 'is-bad'}`} {...tipProps(c?.why || (ok === null ? 'did not apply' : ok ? 'passed' : ''))} />
      </td>
    );
  })}</>;
}

function SideSeg({ label, value, onPick, lock }: { label: string; value: Side; onPick: (s: Side) => void; lock: string | null }) {
  return (
    <span className="bots-tk__side"><span className="bots-tk__side-label">{label}</span>
      <span className="bots-mini-seg" role="radiogroup" aria-label={label}>
        {(['you', 'nova'] as const).map(s => (
          <button key={s} type="button" role="radio" aria-checked={value === s} disabled={lock !== null}
            {...(lock ? whyProps(true, lock) : {})} onClick={() => { if (value !== s) onPick(s); }}>{s === 'you' ? 'You' : 'Nova'}</button>
        ))}
      </span>
    </span>
  );
}

function boardWords(symbol: string, rows: readonly SetupRow[]): string {
  const mine = rows.filter(r => r.symbol === symbol && r.state !== 'watching');
  if (!mine.length) return 'nothing forming';
  const rank = ['triggered', 'near', 'armed', 'pullback', 'leg', 'failed', 'filtered'];
  const best = [...mine].sort((a, b) => rank.indexOf(a.state) - rank.indexOf(b.state))[0];
  return `${setupName(best.setup_type ?? 'first_pullback')} · ${best.state}`;
}

export function BotTickersTable({ today, modes, onModesChanged, boardRows, onOpenSymbol }: {
  /** Today's table, read once for the page (the answer line reads it too). */
  today: { view: TriggersView | null; error: string | null };
  modes: readonly StockModeRow[];
  onModesChanged: () => void;
  boardRows: readonly SetupRow[];
  onOpenSymbol: (symbol: string) => void;
}) {
  const [date, setDate] = useState<string | null>(null);
  const past = useTriggers(date, date !== null);
  const { view, error } = date !== null ? past : today;
  const hot = useHotList();
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [rowError, setRowError] = useState<{ symbol: string; text: string } | null>(null);
  const [draft, setDraft] = useState('');
  const [listError, setListError] = useState<string | null>(null);
  const order = (view?.gates ?? []).map(g => g.id);
  const { listed, unlisted } = orderTickers(view?.tickers ?? [], modes);
  const listLock = hot.busy ? 'Saving the hot list…' : hot.view ? null : (hot.error ?? 'Reading today\'s hot list…');

  const setSides = useCallback(async (symbol: string, buy: Side, sell: Side) => {
    try {
      await putStockMode(symbol, buy, sell);
      setRowError(null);
      onModesChanged();
      void hotListActions.refresh();
    } catch (err) {
      setRowError({ symbol, text: err instanceof Error ? err.message : String(err) });
    }
  }, [onModesChanged]);
  const star = async () => {
    const sym = draft.trim().toUpperCase();
    if (!/^[A-Z][A-Z0-9.]{0,9}$/.test(sym)) { setListError('Type a ticker, like AISP.'); return; }
    const err = await hotListActions.star(sym);
    setListError(err);
    if (!err) setDraft('');
  };
  const toggle = (sym: string) => setOpen(prev => {
    const next = new Set(prev);
    if (next.has(sym)) next.delete(sym); else next.add(sym);
    return next;
  });

  const nowRow = (t: TickerRow, isListed: boolean) => {
    const [buy, sell] = sidesOf(t.symbol, modes);
    const reasons = t.now ? splitReasons(t.now.cells, order) : { own: [], shared: [] };
    const entry = hot.view?.entries.find(e => e.symbol === t.symbol);
    return (
      <tr key={`${t.symbol}-now`} className={isListed ? 'bots-tk__now' : 'bots-tk__unlisted'} data-testid={`bots-tk-${t.symbol}`}>
        <td className="bots-nowrap">
          <button type="button" className={`bots-tk__star${isListed ? ' is-on' : ''}`} disabled={listLock !== null}
            {...(listLock ? whyProps(true, listLock) : tipProps(isListed ? 'On today\'s hot list. Click to take it off.' : 'Add it to today\'s hot list.'))}
            onClick={() => void (isListed ? hotListActions.unstar(t.symbol) : hotListActions.star(t.symbol)).then(e => setRowError(e ? { symbol: t.symbol, text: e } : null))}>
            {isListed ? '★' : '☆'}
          </button>
          <button type="button" className="bots-linkbtn bots-tk__sym" onClick={() => onOpenSymbol(t.symbol)}>{t.symbol}</button>
          {entry ? <span className={`bots-tag bots-tag--${entry.how === 'auto' ? 'auto' : 'pin'}`}>{entry.how === 'auto' ? `auto ${etTime(entry.at)}` : `★ ${etTime(entry.at)}`}</span> : null}
        </td>
        <td className="bots-nowrap">
          {isListed ? (
            <>
              <SideSeg label="Buy" value={buy} lock={null} onPick={s => void setSides(t.symbol, s, sell)} />
              <SideSeg label="Sell" value={sell} lock={null} onPick={s => void setSides(t.symbol, buy, s)} />
              <span className={`bots-tk__who bots-tk__who--${buy}-${sell}`}>{WHO_WORDS[`${buy}/${sell}`]}</span>
            </>
          ) : <span className="bots-muted">not on the list</span>}
        </td>
        <td>{isListed ? <span className="bots-tk__nowtag">now</span> : (
          <button type="button" className="bots-linkbtn" onClick={() => toggle(t.symbol)} aria-expanded={open.has(t.symbol)}>
            {open.has(t.symbol) ? '▾' : '▸'} {t.triggers.length}
          </button>
        )}</td>
        <td className="bots-muted">{boardWords(t.symbol, boardRows)}</td>
        <td className="bots-muted">–</td><td className="bots-muted">–</td>
        <td className="bots-muted bots-nowrap">{daySummary(t)}</td>
        {t.now ? <Squares cells={t.now.cells} order={order} /> : order.map(id => <td key={id} className="bots-tk__g" />)}
        <td className="bots-tk__stop">
          {t.now ? (t.now.answer === 'yes' ? <b className="is-yes">Yes</b> : <>
            <b className="is-no">No</b>{reasons.own.length ? <span> · {reasons.own.join(' · ')}</span> : null}
            {reasons.shared.length ? <span className="bots-muted"> · {reasons.shared.join(', ')}</span> : null}
          </>) : <span className="bots-muted">{date ? 'a past day: no now' : '–'}</span>}
          {rowError?.symbol === t.symbol ? <span className="is-bad"> · {rowError.text}</span> : null}
        </td>
      </tr>
    );
  };
  const triggerRows = (t: TickerRow) => t.triggers.map(x => {
    const res = resultWords(x);
    return (
      <tr key={`${t.symbol}-${x.ts}-${x.setup_type}`} className="bots-tk__past">
        <td /><td />
        <td className="bots-num">{etTime(x.ts)}</td>
        <td>{setupName(x.setup_type)}{x.nth && x.nth > 1 ? <span className="bots-tag bots-tag--tiny">{x.nth === 2 ? '2nd' : `${x.nth}th`}</span> : null}</td>
        <td className="bots-num">{x.grade ?? '–'}</td>
        <td>{x.tape ? <span className={`bots-vbadge bots-vbadge--${x.tape}`}>{x.tape.toUpperCase()}</span> : '–'}</td>
        <td className={`bots-num bots-nowrap bots-tk__res--${res.tone}`}>{res.text}</td>
        <Squares cells={x.cells} order={order} />
        <td className="bots-tk__stop bots-muted">{x.reasons.join(' · ') || 'reached an order'}</td>
      </tr>
    );
  });

  return (
    <section className="bots-card bots-tk" data-testid="bots-tickers">
      <header className="bots-card__head">
        <h3>Tickers today <span className="bots-source">{listed.length} on the hot list{unlisted.length ? ` · ${unlisted.length} more triggered` : ''}</span></h3>
        <span className="bots-card__sub">"now" says whether Nova would buy the ticker if its setup triggered this minute; the rows under it are its triggers today. Same squares; red is what stops it.</span>
      </header>
      <div className="bots-tk__controls">
        <span className="bots-tag bots-tag--auto">Auto</span><span>top</span>
        <span className="bots-mini-seg" role="radiogroup" aria-label="Auto top N">
          {HOT_LIST_AUTO_CHOICES.map(n => (
            <button key={n} type="button" role="radio" aria-checked={hot.view?.auto.n === n} disabled={listLock !== null}
              {...(listLock ? whyProps(true, listLock) : {})} onClick={() => void hotListActions.setAuto(n).then(setListError)}>{n === 0 ? 'Off' : n}</button>
          ))}
        </span>
        <span className="bots-muted">gainers {hot.view?.auto.start ?? '07:00'}–{hot.view?.auto.end ?? '16:00'} by the leaders rule · once in, in for the day · starts empty at 04:00</span>
        <span className="bots-tk__gap" />
        <span className="bots-muted">New names start as</span>
        <SideSeg label="Buy" value={hot.view?.default.buy ?? 'you'} lock={listLock}
          onPick={s => void hotListActions.setDefault(s, hot.view?.default.sell ?? 'you').then(setListError)} />
        <SideSeg label="Sell" value={hot.view?.default.sell ?? 'you'} lock={listLock}
          onPick={s => void hotListActions.setDefault(hot.view?.default.buy ?? 'you', s).then(setListError)} />
        <input className="bots-tk__input" value={draft} placeholder="★ Add a stock" aria-label="Star a stock"
          onChange={e => setDraft(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') void star(); }} />
        <button type="button" className="bots-btn bots-btn--primary" disabled={listLock !== null}
          {...(listLock ? whyProps(true, listLock) : {})} onClick={() => void star()}>★ Add</button>
        {hot.view?.yesterday.length ? (
          <button type="button" className="bots-btn" disabled={listLock !== null} {...(listLock ? whyProps(true, listLock) : {})}
            onClick={() => void hotListActions.bringBack().then(setListError)}>Bring back yesterday's {hot.view.yesterday.length}</button>
        ) : null}
        <input type="date" className="bots-tk__date" aria-label="Day" value={date ?? (view?.date || '')}
          onChange={e => setDate(e.target.value || null)} />
      </div>
      {listError || hot.error || error ? <p className="bots-hero__error" role="alert">{listError ?? hot.error ?? error}</p> : null}
      <div className="bots-tk__wrap">
        <table className="bots-tk__table">
          <thead><tr>
            <th>Ticker</th><th>Who trades it</th><th>When</th><th>Setup</th><th>Gr</th><th>Tape</th><th>Result</th>
            {(view?.gates ?? []).map(g => (
              <th key={g.id} className="bots-tk__g bots-tk__gh" {...tipProps(GATE_TIPS[g.id] ?? g.label, g.label)}><span>{g.label}</span></th>
            ))}
            <th>What stops it</th>
          </tr></thead>
          <tbody>
            <tr className="bots-tk__group"><td colSpan={8 + order.length}>On your hot list · {listed.length} tickers</td></tr>
            {listed.length ? listed.flatMap(t => [nowRow(t, listedOn(hot.view, t.symbol) !== false), ...triggerRows(t)])
              : <tr><td colSpan={8 + order.length} className="bots-muted">Empty. Star a stock, or let the top of the Gainers board fill it from {hot.view?.auto.start ?? '07:00'}.</td></tr>}
            {unlisted.length ? <tr className="bots-tk__group"><td colSpan={8 + order.length}>Triggered today, not on your hot list · {unlisted.length} tickers</td></tr> : null}
            {unlisted.flatMap(t => [nowRow(t, false), ...(open.has(t.symbol) ? triggerRows(t) : [])])}
          </tbody>
        </table>
      </div>
      {view?.impact.length ? (
        <div className="bots-tk__impact" data-testid="bots-tk-impact">
          <b>What each gate did to the day's {view.tickers.reduce((s, t) => s + t.triggers.length, 0)} triggers</b>
          {view.impact.filter(i => i.blocked > 0).map(i => (
            <span key={i.gate}><b>{view.gates.find(g => g.id === i.gate)?.label ?? i.gate}</b> blocked {i.blocked}
              {i.target_first + i.stop_first ? <> · {i.target_first} would have hit target, {i.stop_first} stopped · <span className={i.r < 0 ? 'is-yes' : 'is-no'}>{i.r < 0 ? `${(-i.r).toFixed(1)}R avoided` : `${i.r.toFixed(1)}R missed`}</span></> : null}
            </span>
          ))}
          {view.judgedNow.length ? <span className="bots-muted">Judged with today's settings (nothing recorded them): {view.judgedNow.join(', ').replace(/_/g, ' ')}.</span> : null}
        </div>
      ) : null}
    </section>
  );
}
