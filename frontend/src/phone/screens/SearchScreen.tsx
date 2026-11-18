/**
 * Search (mockup v1, 2026-11-18): Scan's header field, opened, with the phone's keyboard under it.
 *
 * The matches and their order are the desk's own search (`components/globalBarSearchView`): the stocks on
 * the desk's boards first, then every listed stock by ticker or company name. Before anything is typed the
 * screen lists the recent look-ups and today's hot list. Tap a row for the stock page, the blue chip for
 * the Trader; the keyboard's Go opens the first row in the Trader. Nothing scrolls: the screen shows the
 * rows that fit above the keyboard and says how many more there are.
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Search, X } from 'lucide-react';
import { searchView } from '../../components/globalBarSearchView';
import { useSymbolDirectory } from '../../components/symbolDirectory';
import { isRegexInput, parseTickerQuery } from '../../components/tickerSearchQuery';
import { useTickerRecents } from '../../components/tickerSearchRecents';
import { searchTickers } from '../../components/tickerSearchSuggestions';
import { useHotList } from '../../hot_list';
import { useDeskPositions } from '../../ibkr';
import { useIbkrAccountContext } from '../../ibkr/IbkrAccountContext';
import { useLiveScannerFeed } from '../../scanner/ScannerDataContext';
import { useScannerDockRows } from '../../scanner/useScannerDockRows';
import { PhoneScreen, VenuePill } from '../PhoneChrome';
import { pct1, toneOf } from '../phoneFormat';
import { go, goBack, type PhoneRoute } from '../phoneRoute';
import { hotOptions, searchFootText, searchRows, type PhoneSearchRow, type SearchTagSources } from '../phoneSearch';
import { hodCatchTimes } from '../usePhoneHodMomo';
import { rowsThatFit } from '../useRowsThatFit';
import './search.css';

const ROW_PX = 42;
const LABEL_PX = 26;
const FOOT_PX = 26;
const NO_TABS: readonly string[] = [];
const SCAN: PhoneRoute = { screen: 'scan' };
/** The recent rows shown before today's hot list gets the rest of the room. */
const RECENT_ROWS = 4;

function SearchRow({ row, typedHint, onOpen }: {
  row: PhoneSearchRow; typedHint: string; onOpen: (symbol: string, where: 'stock' | 'trade') => void;
}) {
  const tone = toneOf(row.movePct, 1) || 'flat';
  return (
    <div className="ph-find__row" data-testid={`phone-search-row-${row.symbol}`}>
      <button
        type="button"
        className={`ph-chip ph-find__chip${row.symbol.length > 4 ? ' is-long' : ''}`}
        aria-label={`Open ${row.symbol} in the Trader`}
        onClick={() => onOpen(row.symbol, 'trade')}
      >
        <span>
          {row.match ? row.symbol.slice(0, row.match[0]) : row.symbol}
          {row.match ? <mark>{row.symbol.slice(row.match[0], row.match[1])}</mark> : null}
          {row.match ? row.symbol.slice(row.match[1]) : null}
        </span>
        <i aria-hidden="true">›</i>
      </button>
      <div className="ph-find__name">
        <b>{row.typed ? typedHint : row.name ?? row.symbol}</b>
        <i>
          {row.exchange}
          {row.exchange && row.tag ? ' · ' : ''}
          {row.tag ? <em>{row.tag}</em> : null}
        </i>
      </div>
      {row.movePct == null
        ? <span className="ph-find__none">{row.typed ? '' : 'not on a board'}</span>
        : <span className="ph-find__chg" data-tone={tone}>{pct1(row.movePct / 100)}</span>}
      <button type="button" className="ph-rowlink" aria-label={`Open ${row.symbol}'s stock page`} onClick={() => onOpen(row.symbol, 'stock')} />
    </div>
  );
}

export function SearchScreen() {
  const [value, setValue] = useState('');
  const [boxHeight, setBoxHeight] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const feed = useLiveScannerFeed();
  const rows = useScannerDockRows();
  const directory = useSymbolDirectory(true);
  const { recents, remember } = useTickerRecents(NO_TABS);
  const hot = useHotList();
  const account = useIbkrAccountContext();
  const { rows: held, othersBook } = useDeskPositions(account.positions);

  // The tap that opened this screen is what lets the phone raise its keyboard.
  useLayoutEffect(() => {
    inputRef.current?.focus();
  }, []);
  useLayoutEffect(() => {
    const el = boxRef.current;
    if (!el) return undefined;
    const measure = (): void => setBoxHeight(el.clientHeight);
    measure();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  // Search reads no list of its own: the prices that move are the screen's before it.
  const { setL1ActiveTab } = feed;
  useEffect(() => {
    setL1ActiveTab('gainers');
  }, [setL1ActiveTab]);

  const query = useMemo(() => parseTickerQuery(value), [value]);
  const pools = useMemo(() => {
    // The other traders' stocks are offered with yours (ADR 072), as the desk's search offers them.
    const others = [...othersBook].map(([symbol, holds]) => ({ symbol, qty: holds.reduce((n, h) => n + h.qty, 0) }));
    return { tabs: NO_TABS, positions: [...held, ...others], rows, recents, directory: directory.directory };
  }, [held, othersBook, rows, recents, directory.directory]);
  const view = useMemo(() => searchView(query, pools, directory), [query, pools, directory]);
  const total = useMemo(
    () => (query.kind === 'text' || query.kind === 'pattern' ? searchTickers(query, pools, 0).total : 0),
    [query, pools],
  );

  const hotSymbols = useMemo(() => (hot.view?.entries ?? []).map((e) => e.symbol), [hot.view]);
  const tags = useMemo<SearchTagSources>(() => ({
    hodAt: hodCatchTimes(),
    boards: [
      { name: 'Gainers', symbols: feed.gainers.map((r) => r.symbol) },
      { name: 'Gappers', symbols: feed.gappers.map((r) => r.symbol) },
      { name: 'After Hrs', symbols: feed.afterhours.map((r) => r.symbol) },
      { name: 'Losers', symbols: feed.losers.map((r) => r.symbol) },
    ],
    hot: new Set(hotSymbols),
  }), [feed.gainers, feed.gappers, feed.afterhours, feed.losers, hotSymbols]);

  const open = (symbol: string, where: 'stock' | 'trade'): void => {
    remember(symbol);
    go(where === 'trade' ? { screen: 'trade', symbol } : { screen: 'stock', symbol });
  };
  const submit = (ev: FormEvent): void => {
    ev.preventDefault();
    const first = view.options[view.defaultIndex] ?? view.options[0];
    if (first) open(first.symbol, 'trade');
  };

  const matches = searchRows(view.options, tags);
  const browsing = query.kind === 'empty';
  let body;
  if (browsing) {
    // Recent first, then today's hot list in the room that is left; each under its own label.
    const hotOnly = hotSymbols.filter((s) => !recents.includes(s));
    const room = (labels: number): number => rowsThatFit(Math.max(0, boxHeight - labels * LABEL_PX), ROW_PX);
    const labels = (matches.length ? 1 : 0) + (hotOnly.length ? 1 : 0);
    const fit = boxHeight > 0 ? room(labels) : 0;
    const recentShown = matches.slice(0, Math.min(hotOnly.length ? RECENT_ROWS : fit, fit));
    const hotShown = searchRows(
      hotOptions(hot.view?.entries ?? [], hotOnly.slice(0, Math.max(0, fit - recentShown.length)), directory.directory),
      tags,
    );
    body = (
      <>
        {recentShown.length ? (
          <div className="ph-find__label ph-label"><span>Recent</span><span>Tap a row: stock page · chip: Trader</span></div>
        ) : null}
        {recentShown.map((row) => <SearchRow key={row.symbol} row={row} typedHint={view.typedHint} onOpen={open} />)}
        {hotShown.length ? <div className="ph-find__label ph-label"><span>Today&apos;s hot list</span></div> : null}
        {hotShown.map((row) => <SearchRow key={row.symbol} row={row} typedHint={view.typedHint} onOpen={open} />)}
        {!recentShown.length && !hotShown.length && boxHeight > 0 ? (
          <div className="ph-empty" role="status">Type a ticker or a company name.</div>
        ) : null}
      </>
    );
  } else {
    const fit = boxHeight > 0 ? rowsThatFit(Math.max(0, boxHeight - FOOT_PX), ROW_PX) : 0;
    const shown = matches.slice(0, fit);
    // The typed row is the desk's "open anyway", not a match: it is not counted as one.
    const counted = shown.filter((r) => !r.typed).length;
    body = (
      <>
        {shown.map((row) => <SearchRow key={row.symbol} row={row} typedHint={view.typedHint} onOpen={open} />)}
        <div className="ph-find__foot" data-tone={view.footer?.tone ?? 'muted'} role="status" data-testid="phone-search-foot">
          {searchFootText(counted, total, view.footer?.text ?? null)}
        </div>
      </>
    );
  }

  return (
    <PhoneScreen
      name="search"
      tab="scan"
      bar={false}
      header={(
        <form className="ph-head ph-search__head" role="search" onSubmit={submit}>
          <VenuePill />
          <label className="ph-search is-on">
            <Search size={15} aria-hidden="true" />
            <input
              ref={inputRef}
              className="ph-search__input"
              type="text"
              value={value}
              // A regex keeps its case (the desk's rule); everything else is a ticker or a name.
              onChange={(ev) => setValue(isRegexInput(ev.target.value) ? ev.target.value : ev.target.value.toUpperCase())}
              placeholder="Ticker or company"
              aria-label="Search a stock by ticker or company"
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="characters"
              spellCheck={false}
              enterKeyHint="go"
              data-testid="phone-search-input"
            />
            {value ? (
              <button type="button" className="ph-search__clear" aria-label="Clear" onClick={() => { setValue(''); inputRef.current?.focus(); }}>
                <X size={15} aria-hidden="true" />
              </button>
            ) : null}
          </label>
          <button type="button" className="ph-search__cancel" onClick={() => goBack(SCAN)}>Cancel</button>
        </form>
      )}
    >
      <div className="ph-find" ref={boxRef} data-testid="phone-search-rows">{body}</div>
    </PhoneScreen>
  );
}
