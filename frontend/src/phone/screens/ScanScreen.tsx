/**
 * Scan (frozen mockup R2-Scanner): the desk's scanner lists, twelve rows to a page.
 *
 * The rows are the desk's own feed (`ScannerDataProvider`), through the desk's exchange filter and
 * its board chips, so the phone and the desk show one board. A list longer than the screen pages
 * with Prev / Next; nothing scrolls. Tap a row for the stock page, the blue chip for the Trader.
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, ListFilter, Star } from 'lucide-react';
import {
  SCANNER_CHIP_FLOAT_MAX_SHARES,
  SCANNER_CHIP_GAP_MIN_PCT,
  SCANNER_CHIP_IDS,
  SCANNER_CHIP_RELVOL_MIN,
  type ScannerChipId,
} from '../../constantGroups/scanner_board';
import { useCatalystRead } from '../../hooks/useCatalystRead';
import { howListed, useHotList } from '../../hot_list';
import { useLiveScannerFeed } from '../../scanner/ScannerDataContext';
import type { BoardListId } from '../../scanner/boardListForSymbol';
import { listAbsenceText } from '../../scanner/listAbsence';
import { useBoardFilters } from '../../scanner/useBoardFilters';
import { useBoardRows } from '../../scanner/useBoardRows';
import { useSettings } from '../../settings';
import type { ScannerRow } from '../../types/scanner';
import { catalystFace } from '../../utils/catalystCause';
import { readPref, writePref } from '../../utils/prefStore';
import { fmtRvol, fmtVolume } from '../../utils/quoteFormat';
import { LinkPill, PadlockButton, PhoneScreen, RowLink, TickerChip, VenuePill } from '../PhoneChrome';
import { phoneCatalyst } from '../phoneCatalyst';
import { pct1, px, toneOf } from '../phoneFormat';
import { useRowsThatFit } from '../useRowsThatFit';
import './scan.css';

type ScanListId = BoardListId | 'hot_list' | 'hod_momo' | 'running_up' | 'volume_boost' | 'setups';

interface ScanList {
  id: ScanListId;
  name: string;
  /** Why the list cannot be opened here yet; absent when it can. */
  notYet?: string;
}

const NEXT_BUILD = 'Not on the phone yet. It comes in a later build; the desk has it.';

const MAIN_LISTS: readonly ScanList[] = [
  { id: 'gappers', name: 'Gappers' },
  { id: 'gainers', name: 'Gainers' },
  { id: 'losers', name: 'Losers' },
  { id: 'afterhours', name: 'After Hrs' },
];
const MORE_LISTS: readonly ScanList[] = [
  { id: 'large_cap', name: 'Large Cap' },
  { id: 'hot_list', name: 'Hot list' },
  { id: 'hod_momo', name: 'HOD Momo', notYet: NEXT_BUILD },
  { id: 'running_up', name: 'Running Up', notYet: NEXT_BUILD },
  { id: 'volume_boost', name: 'Vol boost', notYet: NEXT_BUILD },
  { id: 'setups', name: 'Setups', notYet: NEXT_BUILD },
];
const ALL_LISTS = [...MAIN_LISTS, ...MORE_LISTS];
const BOARD_LISTS: readonly string[] = ['gappers', 'gainers', 'losers', 'afterhours', 'large_cap'];

const LIST_KEY = 'nova.phone.scan.list';
const ROW_PX = 42;

/** The desk's chips, in the few characters a phone chip holds. The rule behind each is the desk's. */
const CHIP_WORD: Record<ScannerChipId, string> = {
  gap: `Gap ≥${SCANNER_CHIP_GAP_MIN_PCT}%`,
  float: `Float ≤${SCANNER_CHIP_FLOAT_MAX_SHARES / 1_000_000}M`,
  relvol: `RVol ≥${SCANNER_CHIP_RELVOL_MIN}x`,
  news: 'Has news',
  halted: 'Halted',
};

function isBoardList(id: ScanListId): id is BoardListId {
  return BOARD_LISTS.includes(id);
}

function readList(): ScanListId {
  return readPref<ScanListId>(LIST_KEY, 'gappers', (raw) =>
    (ALL_LISTS.some((l) => l.id === raw && !l.notYet) ? (raw as ScanListId) : null));
}

function ScanRow({ row, board, starred, nowMs }: {
  row: ScannerRow; board: BoardListId | null; starred: boolean; nowMs: number;
}) {
  const read = useCatalystRead(row.symbol, board);
  const face = catalystFace(read.read, row.catalyst, nowMs, read.loading);
  const cat = phoneCatalyst({ face, verdict: read.read?.facts?.catalyst ?? row.catalyst, halted: row.halted === true, nowMs });
  const tone = toneOf(row.change_pct == null ? null : row.change_pct * 100, 1);
  return (
    <div className="ph-scan__row" data-testid={`phone-scan-row-${row.symbol}`}>
      <div className="ph-scan__sym">
        <TickerChip symbol={row.symbol} />
        <div className="ph-scan__cat" data-tone={cat.tone}>
          <b>{cat.word}</b>
          <span>
            {cat.when}
            {starred ? <Star className="ph-scan__star" size={9} fill="currentColor" aria-label="On your hot list" /> : null}
          </span>
        </div>
      </div>
      <div className="ph-scan__px">{px(row.price)}</div>
      <div className="ph-scan__chg"><span data-tone={tone || 'flat'}>{pct1(row.change_pct)}</span></div>
      <div className="ph-scan__vol">
        <span>{fmtVolume(row.volume)}</span>
        <i>{fmtRvol(row.rel_volume) ?? ''}</i>
      </div>
      <div className="ph-scan__flt">{fmtVolume(row.float)}</div>
      <RowLink symbol={row.symbol} />
    </div>
  );
}

export function ScanScreen() {
  const feed = useLiveScannerFeed();
  const { exchangeFilter } = useSettings();
  const filters = useBoardFilters();
  const hot = useHotList();
  const [list, setListState] = useState<ScanListId>(readList);
  const [page, setPage] = useState(0);
  const [menu, setMenu] = useState<'more' | 'filter' | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const perPage = useRowsThatFit(bodyRef, ROW_PX);

  const lists = useMemo(() => ({
    gappers: feed.gappers,
    gainers: feed.gainers,
    losers: feed.losers,
    afterhours: feed.afterhours,
    large_cap: feed.largeCap,
  }), [feed.gappers, feed.gainers, feed.losers, feed.afterhours, feed.largeCap]);
  const board = useBoardRows(lists, exchangeFilter.filterRows, filters);

  // The list on screen is the one whose prices the desk's Level 1 budget keeps moving.
  const { setL1ActiveTab } = feed;
  useEffect(() => {
    if (isBoardList(list)) setL1ActiveTab(list);
  }, [list, setL1ActiveTab]);

  const setList = (next: ScanListId): void => {
    writePref(LIST_KEY, next);
    setListState(next);
    setPage(0);
    setMenu(null);
  };

  const meta = ALL_LISTS.find((l) => l.id === list) ?? MAIN_LISTS[0];
  let rows: ScannerRow[];
  let hidden = 0;
  if (isBoardList(list)) {
    rows = board.rows[list];
    hidden = board.hiddenByExchange[list] + board.hiddenByChips[list];
  } else {
    // The hot list names symbols; a row's numbers come from whichever board shows that symbol now.
    const bySymbol = new Map<string, ScannerRow>();
    for (const id of BOARD_LISTS as BoardListId[]) for (const r of lists[id]) if (!bySymbol.has(r.symbol)) bySymbol.set(r.symbol, r);
    rows = (hot.view?.entries ?? []).map((e) => bySymbol.get(e.symbol) ?? ({
      symbol: e.symbol, price: null, prev_close: null, change_pct: e.change_pct, change_abs: null, gap_percent: null,
      volume: null, rel_volume: null, has_news: false, newest_headline_at: null, market_cap: null, float: null,
      short_interest: null, short_ratio: null,
    } satisfies ScannerRow));
  }

  const pages = Math.max(1, Math.ceil(rows.length / perPage));
  const at = Math.min(page, pages - 1);
  useLayoutEffect(() => {
    if (at !== page) setPage(at);
  }, [at, page]);
  const shown = rows.slice(at * perPage, at * perPage + perPage);
  const inMore = MORE_LISTS.some((l) => l.id === list);
  const nowMs = feed.now;

  let empty: string | null = null;
  if (!rows.length) {
    if (list === 'hot_list') empty = hot.error ?? (hot.view ? 'No stocks on today\'s hot list.' : 'Reading the hot list…');
    else empty = listAbsenceText(meta.name, { restError: feed.restError, healthStatus: feed.health.status },
      (title) => (hidden ? `${title}: every row is hidden by your filters.` : `${title}: no rows right now.`));
  }

  return (
    <PhoneScreen
      name="scan"
      tab="scan"
      header={(
        <div className="ph-head">
          <VenuePill />
          <div className="ph-head__title">Scan</div>
          <div className="ph-grow" />
          <LinkPill live />
          <PadlockButton />
        </div>
      )}
    >
      <div className="ph-undertabs ph-scan__tabs">
        {MAIN_LISTS.map((l) => (
          <button key={l.id} type="button" aria-pressed={l.id === list} onClick={() => setList(l.id)}>{l.name}</button>
        ))}
        <button
          type="button"
          aria-pressed={inMore}
          aria-expanded={menu === 'more'}
          data-testid="phone-scan-more"
          onClick={() => setMenu(menu === 'more' ? null : 'more')}
        >
          {inMore ? meta.name : 'More'}
          <ChevronDown size={12} aria-hidden="true" />
        </button>
        {menu === 'more' ? (
          <div className="ph-menu ph-scan__more" role="menu">
            {MORE_LISTS.map((l) => (
              <button
                key={l.id}
                type="button"
                role="menuitemradio"
                aria-checked={l.id === list}
                disabled={Boolean(l.notYet)}
                data-why={l.notYet}
                onClick={() => setList(l.id)}
              >
                {l.name}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      <div className="ph-scan__filters">
        <ListFilter size={14} aria-hidden="true" />
        {SCANNER_CHIP_IDS.filter((id) => filters.active.has(id)).map((id) => (
          <button key={id} type="button" className="is-on" aria-pressed="true" onClick={() => filters.toggle(id)}>
            {CHIP_WORD[id]}
          </button>
        ))}
        <button
          type="button"
          aria-expanded={menu === 'filter'}
          data-testid="phone-scan-filter"
          onClick={() => setMenu(menu === 'filter' ? null : 'filter')}
        >
          + Filter
        </button>
        {menu === 'filter' ? (
          <div className="ph-menu ph-scan__filtermenu" role="menu">
            {SCANNER_CHIP_IDS.map((id) => (
              <button
                key={id}
                type="button"
                role="menuitemcheckbox"
                aria-checked={filters.active.has(id)}
                onClick={() => { filters.toggle(id); setPage(0); }}
              >
                {CHIP_WORD[id]}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      <div className="ph-scan__head">
        <div>Symbol</div>
        <div>Price</div>
        <div>Change</div>
        <div>Volume</div>
        <div>Float</div>
      </div>

      <div className="ph-scan__rows" ref={bodyRef} data-testid="phone-scan-rows">
        {empty ? <div className="ph-empty" role="status">{empty}</div> : shown.map((row) => (
          <ScanRow
            key={row.symbol}
            row={row}
            board={isBoardList(list) ? list : null}
            starred={howListed(hot.view, row.symbol) === 'star'}
            nowMs={nowMs}
          />
        ))}
      </div>

      <div className="ph-scan__foot">
        <div data-testid="phone-scan-count">
          {rows.length ? `${at * perPage + 1} to ${Math.min(rows.length, (at + 1) * perPage)} of ${rows.length}` : '0 rows'}
          {hidden ? ` · ${hidden} hidden` : ''}
        </div>
        <div className="ph-scan__pager">
          <button type="button" className="ph-pill-btn" disabled={at === 0} data-why="This is the first page." onClick={() => setPage(at - 1)}>‹ Prev</button>
          <button type="button" className="ph-pill-btn" disabled={at >= pages - 1} data-why="This is the last page." onClick={() => setPage(at + 1)}>Next ›</button>
        </div>
      </div>
    </PhoneScreen>
  );
}
