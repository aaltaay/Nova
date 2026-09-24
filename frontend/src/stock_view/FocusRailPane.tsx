/**
 * One half of the Focus rail: a list picker header, sortable column headers
 * and the rows of one mirrored list. The upper half is the rail the operator
 * had; the lower half (operator ask 2026-09-24: "I wanna see HOD all the
 * time") is the same pane on its own list, HOD Momo unless another is picked,
 * and folds to its header. Each half keeps its own cursor (↑ ↓, Enter) and
 * hover card. The rail (FocusRail.tsx) reads the feeds and hands each half its
 * rows, or what their absence says; this file only draws and listens.
 */
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { ArrowDown, ArrowUp, ChevronDown } from 'lucide-react';
import { openBotSymbolMenu } from '../bot';
import { NewsCell } from '../components/NewsCell';
import { watchMarkTitle } from '../watch_list';
import {
  FOCUS_RAIL_BOT_HELD_TITLE,
  FOCUS_RAIL_BOT_QUIET_TITLE,
  FOCUS_RAIL_CARD_HIDE_MS,
  FOCUS_RAIL_REC_TITLE,
  FOCUS_RAIL_SORT_LABELS,
  FOCUS_RAIL_SORT_RESET,
  FOCUS_RAIL_SORT_TITLES,
} from '../constantGroups/trader_chrome';
import { TRADER_TAB_GAP_TITLE } from '../constantGroups/trader_view';
import { SIM_FOCUS_RAIL_REPLAY_NOTE } from '../sim';
import type { NovaModule } from '../workspace';
import { stepCursor, type FocusRow } from './focusRailState';
import { FocusRailHoverCard, hasStatus, type FocusRailHover } from './FocusRailHoverCard';
import { nextFocusSort, type FocusSort, type FocusSortKey } from './focusRailSort';
import { formatSignedPct, pctTone } from './tabContext';

/** What both halves draw with, read once by the rail. */
export interface FocusPaneShared {
  /** Sim off the live edge with no board at the playhead: live values stay off the rows. */
  replayDesk: boolean;
  watchList: readonly string[];
  isAllowed: (symbol: string) => boolean;
  isRecording: (symbol: string) => boolean;
  /** The Trader's active symbol, upper-case, or null. */
  active: string | null;
  traderLiveTabs: readonly string[];
  open: (symbol: string) => void;
  modules: readonly NovaModule[];
}

/** One half's list, as the rail read it. */
export interface FocusPaneView {
  list: string;
  /** The list's name in the picker. */
  title: string;
  /** Sorted rows; null when this desk does not carry the list. */
  rows: FocusRow[] | null;
  /** What the half says while it has no rows. */
  absent: string;
  /** The sort in force (a Sim replay desk keeps only the symbol sort). */
  sort: FocusSort | null;
}

/** One sortable column header; the active one shows its direction. */
function SortHeader({ tid, column, sort, onSort }: {
  tid: string; column: FocusSortKey; sort: FocusSort | null; onSort: (key: FocusSortKey) => void;
}) {
  const on = sort?.key === column ? sort.dir : null;
  const Arrow = on === 'asc' ? ArrowUp : ArrowDown;
  return (
    <button type="button" className={`focus-rail__th focus-rail__th--${column}${on ? ' is-sorted' : ''}`}
      aria-sort={on === 'asc' ? 'ascending' : on === 'desc' ? 'descending' : 'none'}
      title={on ? `${FOCUS_RAIL_SORT_TITLES[column]} · ${FOCUS_RAIL_SORT_RESET}` : FOCUS_RAIL_SORT_TITLES[column]}
      data-testid={`${tid}-sort-${column}`} data-dir={on ?? ''} onClick={() => onSort(column)}>
      {FOCUS_RAIL_SORT_LABELS[column]}
      {on && <Arrow size={9} aria-hidden="true" />}
    </button>
  );
}

export interface FocusRailPaneProps {
  /** Test-id prefix: `focus-rail` for the upper half, `focus-rail-lower` for the lower. */
  tid: string;
  half: 'upper' | 'lower';
  view: FocusPaneView;
  onPick: (list: string) => void;
  onSort: (sort: FocusSort | null) => void;
  shared: FocusPaneShared;
  /** The header's leading word ("Focus" on the upper half); none on the lower. */
  title?: string;
  pickAria: string;
  /** The header's trailing control: collapse the rail, or fold this half. */
  control: ReactNode;
  /** Folded to its header (the lower half only). */
  folded?: boolean;
}

export function FocusRailPane({ tid, half, view, onPick, onSort: setSort, shared, title, pickAria, control, folded = false }: FocusRailPaneProps) {
  const { replayDesk, watchList, isAllowed, isRecording, active, traderLiveTabs, open, modules } = shared;
  const { list, title: listTitle, rows, absent, sort } = view;
  const [cursor, setCursor] = useState(-1);
  const [hover, setHover] = useState<FocusRailHover | null>(null);
  const hideTimer = useRef<number | null>(null);

  const keepCard = useCallback(() => {
    if (hideTimer.current != null) window.clearTimeout(hideTimer.current);
    hideTimer.current = null;
  }, []);
  // A short grace, so the pointer can cross the row into the card.
  const hideCard = useCallback(() => {
    keepCard();
    hideTimer.current = window.setTimeout(() => { hideTimer.current = null; setHover(null); }, FOCUS_RAIL_CARD_HIDE_MS);
  }, [keepCard]);
  useEffect(() => keepCard, [keepCard]);
  const showCard = (target: HTMLElement, card: Omit<FocusRailHover, 'anchor'>) => {
    keepCard();
    const r = (target.closest('.focus-rail__row') ?? target).getBoundingClientRect();
    setHover({ ...card, anchor: { left: r.left, top: r.top, right: r.right, bottom: r.bottom } });
  };

  useEffect(() => { setCursor(-1); setHover(null); }, [list, sort?.key, sort?.dir, folded]);
  const onSort = (key: FocusSortKey) => setSort(nextFocusSort(sort, key));

  const onKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (folded || !rows?.length) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      setCursor(current => stepCursor(current, event.key === 'ArrowDown' ? 1 : -1, rows.length));
    } else if (event.key === 'Enter' && cursor >= 0 && rows[cursor]) {
      event.preventDefault();
      open(rows[cursor].symbol);
    }
  };

  const count = rows ? ` ${rows.length}` : '';
  return (
    <section className={`focus-rail__pane focus-rail__pane--${half}${folded ? ' focus-rail__pane--folded' : ''}`}
      aria-label={listTitle} data-testid={`focus-rail-pane-${half}`} data-folded={folded ? '1' : '0'}
      tabIndex={folded ? undefined : 0} onKeyDown={onKeyDown}>
      <div className="focus-rail__head">
        <label className="focus-rail__src" title={pickAria}>
          {title && <span className="focus-rail__title">{title}</span>}
          <span className={`focus-rail__list${title ? '' : ' focus-rail__list--lead'}`} data-testid={`${tid}-list-label`}>
            {title ? `· ${listTitle}${count}` : `${listTitle}${count}`}
          </span>
          <ChevronDown size={10} aria-hidden="true" />
          <select className="focus-rail__pick" aria-label={pickAria} data-testid={`${tid}-pick`}
            value={list} onChange={event => onPick(event.target.value)}>
            {modules.map(m => <option key={m.id} value={m.id}>{m.title}</option>)}
          </select>
        </label>
        {control}
      </div>
      {!folded && rows != null && rows.length > 0 && (
        <div className="focus-rail__cols" data-testid={`${tid}-cols`}>
          {replayDesk ? <span className="focus-rail__news" /> : <SortHeader tid={tid} column="news" sort={sort} onSort={onSort} />}
          <span className="focus-rail__dots" />
          <SortHeader tid={tid} column="symbol" sort={sort} onSort={onSort} />
          {!replayDesk && (
            <>
              <SortHeader tid={tid} column="price" sort={sort} onSort={onSort} />
              <SortHeader tid={tid} column="gap" sort={sort} onSort={onSort} />
            </>
          )}
        </div>
      )}
      {!folded && (
        <div className="focus-rail__rows" role="listbox" aria-label={listTitle} data-testid={`${tid}-rows`}
          onScroll={() => setHover(null)}>
          {replayDesk && rows != null && rows.length > 0 && (
            <p className="focus-rail__absent" data-testid={`${tid}-replay-note`}>{SIM_FOCUS_RAIL_REPLAY_NOTE}</p>
          )}
          {rows == null || rows.length === 0 ? (
            <p className="focus-rail__absent" data-testid={`${tid}-absent`}>{absent}</p>
          ) : rows.map((row, index) => {
            const recording = isRecording(row.symbol);
            const allowed = isAllowed(row.symbol);
            const held = allowed && (recording || traderLiveTabs.includes(row.symbol));
            const isActive = row.symbol === active;
            // One card for the row, from the circle or the dots (news first, then status).
            const card = { row, news: !replayDesk, recording, allowed, held };
            const openCard = card.news || hasStatus(card)
              ? (event: React.MouseEvent<HTMLElement>) => showCard(event.currentTarget, card)
              : undefined;
            return (
              <div
                key={row.symbol}
                role="option"
                aria-selected={isActive}
                className={`focus-rail__row${isActive ? ' is-active' : ''}${index === cursor ? ' is-cursor' : ''}`}
                data-testid={`${tid}-row-${row.symbol}`}
                onClick={() => { setCursor(index); open(row.symbol); }}
                onContextMenu={event => {
                  event.preventDefault();
                  openBotSymbolMenu(row.symbol, event.clientX, event.clientY);
                }}
                onMouseEnter={() => { if (hover?.row.symbol === row.symbol) keepCard(); }}
                onMouseLeave={hideCard}
              >
                <span className="focus-rail__news" data-testid={`${tid}-news-${row.symbol}`}
                  onMouseEnter={card.news ? openCard : undefined}>
                  {!replayDesk && row.newsKnown && <NewsCell newest_headline_at={row.headlineAt} catalyst={row.verdict} plain />}
                </span>
                <span className="focus-rail__dots" data-testid={`${tid}-dots-${row.symbol}`} onMouseEnter={openCard}>
                  {recording && <i className="focus-rail__dot focus-rail__dot--rec" aria-label={FOCUS_RAIL_REC_TITLE} data-testid={`${tid}-rec-${row.symbol}`} />}
                  {allowed && (
                    <i className={`focus-rail__dot focus-rail__dot--bot${held ? '' : ' focus-rail__dot--quiet'}`}
                      aria-label={held ? FOCUS_RAIL_BOT_HELD_TITLE : FOCUS_RAIL_BOT_QUIET_TITLE}
                      data-testid={`${tid}-bot-${row.symbol}`} data-held={held ? '1' : '0'} />
                  )}
                </span>
                {watchList.includes(row.symbol) ? (
                  <span className="focus-rail__sym is-watched" title={watchMarkTitle(row.symbol)}
                    data-testid={`${tid}-watched-${row.symbol}`}>{row.symbol}</span>
                ) : (
                  <span className="focus-rail__sym">{row.symbol}</span>
                )}
                {!replayDesk && (
                  <>
                    <span className={`focus-rail__px${row.priceTitle ? ' focus-rail__px--alert' : ''}`} title={row.priceTitle}
                      data-testid={`${tid}-px-${row.symbol}`}>
                      {row.price != null ? row.price.toFixed(2) : '—'}
                    </span>
                    <span className={`focus-rail__gap focus-rail__gap--${pctTone(row.gapPct)}`} title={TRADER_TAB_GAP_TITLE}>
                      {formatSignedPct(row.gapPct)}
                    </span>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
      {hover && <FocusRailHoverCard hover={hover} onEnter={keepCard} onLeave={hideCard} />}
    </section>
  );
}
