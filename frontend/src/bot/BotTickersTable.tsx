/**
 * Tickers today (ADR 044, amended 2026-10-06): today's hot list (★ yours, ☆ auto), the stocks set to bot entry,
 * and the squares, by ticker. Each has a "now" row -- would the bot trade it if one of its strategies triggered
 * this minute -- with its Entry / Exit switch, and under it every trigger of the day on it, judged by the same
 * checks; red is what stopped it. Tickers that only triggered fold at the end. Under the table, what each gate
 * did to the day's triggers. The star is watching only: it never sets Entry / Exit.
 *
 * One table for both sides (ADR 049, #778 step 5): long and short triggers mixed, each setup with its ▲ LONG /
 * ▼ SHORT tag. The squares of every trade end with "not against you"; behind an orange divider, the shorts-only
 * block (borrow, SSR, no halt in 10 min, margin 25%, before 15:50), which a long trigger leaves empty. The SSR
 * square is never red: amber, "SSR · at the ask".
 */
import { useCallback, useEffect, useState } from 'react';
import { SETUP_SIDE_TAG } from '../constantGroups/short_setups';
import { HOT_LIST_AUTO_CHOICES, hotListActions, listedOn, useHotList } from '../hot_list';
import { putStockMode } from '../stock_read';
import { tipProps, whyProps } from '../ux';
import { setupName } from './botsPageFormat';
import { etTime } from './botWhen';
import type { StockModeRow } from './stockModesApi';
import { allStops, daySummary, GATE_TIPS, orderTickers, resultWords, sidesOf, splitReasons, WHO_WORDS, type Side, type Stop } from './tickerTable';
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

function Square({ id, c, divider }: { id: string; c: Cells[string] | undefined; divider: boolean }) {
  const ok = c ? c.ok : null;
  const tone = ok === null ? 'is-na' : !ok ? 'is-bad' : c?.warn ? 'is-warn' : 'is-ok';
  return (
    <td className={`bots-tk__g${divider ? ' bots-tk__g--divider' : ''}`} data-gate={id}>
      <span className={`bots-tk__cell ${tone}`} {...tipProps(c?.why || (ok === null ? 'did not apply' : ok ? 'passed' : ''))} />
    </td>
  );
}

/** Every trade's squares, then the shorts-only block behind the orange divider: empty where a row has none of
 * them (a long trigger, a stock with no short strategy On). */
function Squares({ cells, order, shortOrder }: { cells: Cells; order: readonly string[]; shortOrder: readonly string[] }) {
  const shortBlock = shortOrder.some(id => cells[id]);
  return <>
    {order.map(id => <Square key={id} id={id} c={cells[id]} divider={false} />)}
    {shortOrder.map((id, i) => (shortBlock ? <Square key={id} id={id} c={cells[id]} divider={i === 0} />
      : <td key={id} className={`bots-tk__g${i === 0 ? ' bots-tk__g--divider' : ''}`} />))}
  </>;
}

/** The reds in a few words, each with the backend's whole sentence on hover; `muted` for the shared ones. */
function Stops({ stops, muted = false }: { stops: readonly Stop[]; muted?: boolean }) {
  return <>{stops.map((s, i) => (
    <span key={s.id} className={muted ? 'bots-muted' : 'bots-tk__stopword'} {...tipProps(s.why || s.word, s.word)}>
      {i ? ' · ' : ''}{s.word}
    </span>
  ))}</>;
}

/** The setup's name with its side, in words beside the arrow (ADR 049). */
function SetupWithSide({ setup, side }: { setup: string; side: 'long' | 'short' }) {
  return (
    <>
      <span className={`bots-sidetag bots-sidetag--${side} bots-tk__sidetag`}>{SETUP_SIDE_TAG[side]}</span>{' '}
      {setupName(setup)}
    </>
  );
}

function SideSeg({ label, value, onPick, lock }: { label: string; value: Side; onPick: (s: Side) => void; lock: string | null }) {
  return (
    <span className="bots-tk__side"><span className="bots-tk__side-label">{label}</span>
      <span className="bots-mini-seg" role="radiogroup" aria-label={label}>
        {(['you', 'nova'] as const).map(s => (
          <button key={s} type="button" role="radio" aria-checked={value === s} disabled={lock !== null}
            {...(lock ? whyProps(true, lock) : {})} onClick={() => { if (value !== s) onPick(s); }}>{s === 'you' ? 'You' : 'Bot'}</button>
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
  const [showUnlisted, setShowUnlisted] = useState(false);
  const [rowError, setRowError] = useState<{ symbol: string; text: string } | null>(null);
  const [draft, setDraft] = useState('');
  const [listError, setListError] = useState<string | null>(null);
  const order = (view?.gates ?? []).map(g => g.id);
  const shortOrder = (view?.shortGates ?? []).map(g => g.id);
  const every = [...order, ...shortOrder];
  const cols = 8 + every.length;
  const { today: listed, others: unlisted } = orderTickers(view?.tickers ?? [], modes);
  const starred = hot.view?.entries.length ?? 0;
  const listLock = hot.busy ? 'Saving the hot list…' : hot.view ? null : (hot.error ?? 'Reading today\'s hot list…');

  const setSides = useCallback(async (symbol: string, buy: Side, sell: Side) => {
    try {
      await putStockMode(symbol, buy, sell);
      setRowError(null);
      onModesChanged();
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

  const nowRow = (t: TickerRow, isToday: boolean) => {
    const [buy, sell] = sidesOf(t.symbol, modes);
    const reasons = t.now ? splitReasons(t.now.cells, every) : { own: [], shared: [] };
    const entry = hot.view?.entries.find(e => e.symbol === t.symbol);
    const isListed = listedOn(hot.view, t.symbol) === true;
    return (
      <tr key={`${t.symbol}-now`} className={isToday ? 'bots-tk__now' : 'bots-tk__unlisted'} data-testid={`bots-tk-${t.symbol}`}>
        <td className="bots-nowrap">
          <button type="button" className={`bots-tk__star${isListed ? ' is-on' : ''}`} disabled={listLock !== null}
            {...(listLock ? whyProps(true, listLock) : tipProps(isListed
              ? `On today's hot list (${entry?.how === 'auto' ? 'an auto ☆' : 'your ★'}): the scanners follow it all day. Click to take it off. Who trades it stays as it is.`
              : 'Star it onto today\'s hot list: the scanners follow it all day. A star never lets the bot trade it: that is Entry / Exit.'))}
            onClick={() => void (isListed ? hotListActions.unstar(t.symbol) : hotListActions.star(t.symbol)).then(e => setRowError(e ? { symbol: t.symbol, text: e } : null))}>
            {isListed && entry?.how !== 'auto' ? '★' : '☆'}
          </button>
          <button type="button" className="bots-linkbtn bots-tk__sym" onClick={() => onOpenSymbol(t.symbol)}>{t.symbol}</button>
          {entry ? <span className={`bots-tag bots-tag--${entry.how === 'auto' ? 'auto' : 'pin'}`}>{entry.how === 'auto' ? `auto ${etTime(entry.at)}` : `★ ${etTime(entry.at)}`}</span> : null}
          {entry && entry.followed !== true ? (
            <span className="bots-tag bots-tag--warn" data-testid={`bots-tk-unfollowed-${t.symbol}`}
              {...tipProps(entry.why_not_followed ?? 'Whether the scanners follow it could not be read.', 'Not followed by the scanners')}>
              {entry.followed === false ? 'not followed' : 'followed?'}
            </span>
          ) : null}
        </td>
        <td className="bots-nowrap">
          <SideSeg label="Entry" value={buy} lock={null} onPick={s => void setSides(t.symbol, s, sell)} />
          <SideSeg label="Exit" value={sell} lock={null} onPick={s => void setSides(t.symbol, buy, s)} />
          <span className={`bots-tk__who bots-tk__who--${buy}-${sell}`}>{WHO_WORDS[`${buy}/${sell}`]}</span>
        </td>
        <td>{isToday ? <span className="bots-tk__nowtag">now</span> : (
          <button type="button" className="bots-linkbtn" onClick={() => toggle(t.symbol)} aria-expanded={open.has(t.symbol)}>
            {open.has(t.symbol) ? '▾' : '▸'} {t.triggers.length}
          </button>
        )}</td>
        <td className="bots-muted bots-nowrap">{isToday ? boardWords(t.symbol, boardRows) : '–'}</td>
        <td className="bots-muted">–</td><td className="bots-muted">–</td>
        <td className="bots-muted bots-nowrap">{daySummary(t)}</td>
        {t.now ? <Squares cells={t.now.cells} order={order} shortOrder={shortOrder} />
          : every.map((id, i) => <td key={id} className={`bots-tk__g${i === order.length ? ' bots-tk__g--divider' : ''}`} />)}
        <td className="bots-tk__stop">
          {t.now ? (t.now.answer === 'yes' ? <b className="is-yes">Yes</b> : <>
            <b className="is-no">No</b>
            {reasons.own.length ? <> · <Stops stops={reasons.own} /></> : null}
            {reasons.shared.length ? <span className="bots-muted"> · <Stops stops={reasons.shared} muted /></span> : null}
          </>) : <span className="bots-muted">{date ? 'a past day: no now' : '–'}</span>}
          {rowError?.symbol === t.symbol ? <span className="is-bad"> · {rowError.text}</span> : null}
        </td>
      </tr>
    );
  };
  const triggerRows = (t: TickerRow) => t.triggers.map(x => {
    const res = resultWords(x);
    const reds = allStops(x.cells, every, x);
    return (
      <tr key={`${t.symbol}-${x.ts}-${x.setup_type}`} className="bots-tk__past">
        <td /><td />
        <td className="bots-num bots-nowrap">{etTime(x.ts)}</td>
        <td className="bots-nowrap"><SetupWithSide setup={x.setup_type} side={x.side} />{x.nth && x.nth > 1 ? <span className="bots-tag bots-tag--tiny">{x.nth === 2 ? '2nd' : `${x.nth}th`}</span> : null}</td>
        <td className="bots-num">{x.grade ?? '–'}</td>
        <td>{x.tape ? <span className={`bots-vbadge bots-vbadge--${x.tape}`}>{x.tape.toUpperCase()}</span> : '–'}</td>
        <td className={`bots-num bots-nowrap bots-tk__res--${res.tone}`}>{res.text}</td>
        <Squares cells={x.cells} order={order} shortOrder={shortOrder} />
        <td className="bots-tk__stop">{reds.length ? <Stops stops={reds} /> : <span className="is-yes">every check passed</span>}</td>
      </tr>
    );
  });

  return (
    <section className="bots-card bots-tk" data-testid="bots-tickers">
      <header className="bots-card__head">
        <h3>Tickers today <span className="bots-source">{starred} on the hot list{listed.length > starred ? ` · ${listed.length - starred} more set to bot entry` : ''}{unlisted.length ? ` · ${unlisted.length} more triggered` : ''}</span></h3>
        <span className="bots-card__sub">"now" says whether the bot would trade the ticker if one of its strategies triggered this minute, long or short; the rows under it are its triggers today. Same squares, the shorts-only block behind the orange line; red is what stops it, amber passes and says what it changed. The ★ is watching only: Entry / Exit decides who trades.</span>
      </header>
      <div className="bots-tk__controls">
        <span className="bots-tag bots-tag--auto">Auto</span><span>top</span>
        <span className="bots-mini-seg" role="radiogroup" aria-label="Auto top N">
          {HOT_LIST_AUTO_CHOICES.map(n => (
            <button key={n} type="button" role="radio" aria-checked={hot.view?.auto.n === n} disabled={listLock !== null}
              {...(listLock ? whyProps(true, listLock) : {})} onClick={() => void hotListActions.setAuto(n).then(setListError)}>{n === 0 ? 'Off' : n}</button>
          ))}
        </span>
        <span className="bots-muted" {...tipProps(hot.view?.auto.rule ?? 'The top of the live Gainers board by the leaders rule.', 'Auto')}>
          gainers {hot.view?.auto.start ?? '07:00'}–{hot.view?.auto.end ?? '16:00'} by the leaders rule · once in, in for the day · starts empty at 04:00
        </span>
        {hot.view?.auto.error ? <span className="bots-tag bots-tag--warn" data-testid="bots-tk-auto-error"
          {...tipProps(hot.view.auto.error, 'The auto feed')}>auto feed: not reading the board</span> : null}
        <span className="bots-tk__gap" />
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
          <thead>
            {shortOrder.length ? (
              <tr className="bots-tk__grouphead">
                <th colSpan={7 + order.length} />
                <th colSpan={shortOrder.length} className="bots-tk__shorthead" data-testid="bots-tk-short-head"
                  {...tipProps('The short check\'s own squares. A long trigger leaves them empty.', 'Shorts only')}>
                  {SETUP_SIDE_TAG.short} only
                </th>
                <th />
              </tr>
            ) : null}
            <tr>
              <th>Ticker</th><th>Who trades it</th><th>When</th><th>Setup</th><th>Gr</th><th>Tape</th><th>Result</th>
              {(view?.gates ?? []).map(g => (
                <th key={g.id} className="bots-tk__g bots-tk__gh" {...tipProps(GATE_TIPS[g.id] ?? g.label, g.label)}><span>{g.label}</span></th>
              ))}
              {(view?.shortGates ?? []).map((g, i) => (
                <th key={g.id} className={`bots-tk__g bots-tk__gh bots-tk__gh--short${i === 0 ? ' bots-tk__g--divider' : ''}`}
                  {...tipProps(GATE_TIPS[g.id] ?? g.label, g.label)}><span>{g.label}</span></th>
              ))}
              <th>What stops it</th>
            </tr>
          </thead>
          <tbody>
            <tr className="bots-tk__group"><td colSpan={cols}>On your hot list or set to bot entry · {listed.length} tickers</td></tr>
            {listed.length ? listed.flatMap(t => [nowRow(t, true), ...triggerRows(t)])
              : <tr><td colSpan={cols} className="bots-muted">Empty. Star a stock, set one to bot entry, or let the top of the Gainers board fill the hot list from {hot.view?.auto.start ?? '07:00'}.</td></tr>}
            {unlisted.length ? (
              <tr className="bots-tk__group">
                <td colSpan={cols}>
                  <button type="button" className="bots-linkbtn bots-tk__fold" aria-expanded={showUnlisted}
                    onClick={() => setShowUnlisted(v => !v)} data-testid="bots-tk-unlisted-toggle">
                    {showUnlisted ? '▾' : '▸'} Triggered today, not on your hot list or set to bot entry · {unlisted.length} tickers ·{' '}
                    {unlisted.reduce((n, t) => n + t.triggers.length, 0)} triggers
                  </button>
                </td>
              </tr>
            ) : null}
            {showUnlisted ? unlisted.flatMap(t => [nowRow(t, false), ...(open.has(t.symbol) ? triggerRows(t) : [])]) : null}
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
