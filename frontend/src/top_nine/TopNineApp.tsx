/**
 * The Top 9 pop-up's page (`?view=top9`, main.tsx): the desk window's lists, nine tiles at a time.
 *
 * Single source of truth, both ways: the boards come from the desk window's scanner feed
 * (TopNinePublisher), and a double-click asks the desk window to open the symbol in its Trader
 * (workspace requestOpenOnDesk) -- the same open a ticker click runs there, under its preview-tab
 * rule and live Level 2 cap. This window holds no Trader tabs and opens no scanner socket.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { etChartSeconds } from '../tickerChartData';
import { requestOpenOnDesk } from '../workspace';
import {
  TOP_NINE_AFTER_HOURS_EMPTY,
  TOP_NINE_DESK_SILENT,
  TOP_NINE_DESK_SILENT_MS,
  TOP_NINE_LIST_EMPTY,
  TOP_NINE_LIST_KEY,
  TOP_NINE_LISTS,
  TOP_NINE_NO_DESK,
  TOP_NINE_OPEN_WAIT_MS,
  TOP_NINE_SIZE,
  TOP_NINE_TITLE,
  type TopNineList,
} from './topNineConstants';
import { readTopNineList, writeTopNineList } from './topNineNav';
import type { TopNineSwitch } from './topNineMarks';
import { TopNineHeader } from './TopNineHeader';
import { TopNineSwitchLog } from './TopNineSwitchLog';
import { TopNineTile } from './TopNineTile';
import { TopNineTileMenu, type TopNineMenuAt } from './TopNineTileMenu';
import { useTileSlide } from './useTileSlide';
import { useTopNineAlerts } from './useTopNineAlerts';
import { useTopNineFeed } from './useTopNineFeed';
import './topNine.css';

const NOTICE_MS = 6_000;

function useNow(ms: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(timer);
  }, [ms]);
  return now;
}

function emptyText(list: TopNineList, label: string): string {
  return list === 'afterhours' ? TOP_NINE_AFTER_HOURS_EMPTY : TOP_NINE_LIST_EMPTY(label);
}

export default function TopNineApp() {
  const [list, setListState] = useState<TopNineList>(() => readTopNineList());
  const [onTop, setOnTop] = useState<boolean | null>(() =>
    typeof window.novaDesktop?.setKeepOnTop === 'function' ? false : null);
  const [opening, setOpening] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [menu, setMenu] = useState<TopNineMenuAt | null>(null);
  const listRef = useRef(list);
  listRef.current = list;

  // The feed calls back on a switch; the sound hook, below it, answers.
  const onSwitchRef = useRef<(l: TopNineList, s: TopNineSwitch) => void>(() => undefined);
  const feed = useTopNineFeed((switchedList, switched) => onSwitchRef.current(switchedList, switched));
  const alerts = useTopNineAlerts(list, feed.snapshot);
  onSwitchRef.current = alerts.onSwitch;
  const now = useNow(1_000);
  const label = TOP_NINE_LISTS.find((l) => l.list === list)?.label ?? list;

  // A grid button on the desk's rail switches this window's list through the shared key.
  useEffect(() => {
    const onStorage = (ev: StorageEvent) => {
      if (ev.key === TOP_NINE_LIST_KEY) setListState(readTopNineList());
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  useEffect(() => {
    document.title = `${TOP_NINE_TITLE} · ${label}`;
  }, [label]);

  useEffect(() => {
    if (!notice) return undefined;
    const timer = window.setTimeout(() => setNotice(null), NOTICE_MS);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const chooseList = useCallback((next: TopNineList) => {
    writeTopNineList(next);
    setListState(next);
  }, []);

  const openMenu = useCallback((symbol: string, x: number, y: number) => setMenu({ symbol, x, y }), []);
  const closeMenu = useCallback(() => setMenu(null), []);

  const chooseOnTop = useCallback((on: boolean) => {
    const set = window.novaDesktop?.setKeepOnTop;
    if (typeof set !== 'function') return;
    void set(on).then(
      (state) => setOnTop(Boolean(state)),
      (err: unknown) => console.warn('[nova] keep on top was not set', err),
    );
  }, []);

  // One request per symbol at a time: a ticker click inside a double-clicked tile asks once.
  const inFlight = useRef(new Set<string>());
  const openInTrader = useCallback((symbol: string) => {
    if (inFlight.current.has(symbol)) return;
    inFlight.current.add(symbol);
    setOpening(symbol);
    void requestOpenOnDesk(symbol, { from: listRef.current, waitMs: TOP_NINE_OPEN_WAIT_MS }).then((ok) => {
      inFlight.current.delete(symbol);
      setOpening((cur) => (cur === symbol ? null : cur));
      setNotice(ok ? null : TOP_NINE_NO_DESK);
    });
  }, []);

  const snapshot = feed.snapshot;
  const board = snapshot?.lists[list];
  const marks = feed.marks[list];
  const silent = !snapshot || now - feed.receivedAt > TOP_NINE_DESK_SILENT_MS;
  const rows = silent ? [] : board?.rows ?? [];
  const refFor = useTileSlide(rows.map((r) => r.symbol).join(','));
  const endTime = snapshot ? etChartSeconds(snapshot.asOf * 1000) : null;

  const source = silent ? null : snapshot?.source ?? null;
  let empty: string | null = null;
  if (silent) empty = TOP_NINE_DESK_SILENT;
  else if (source?.kind === 'unknown') empty = source.why;
  else if (!rows.length) empty = emptyText(list, label);

  return (
    <div className="top-nine-app" data-testid="top-nine-app" data-list={list}>
      <TopNineHeader
        list={list}
        onList={chooseList}
        snapshot={silent ? null : snapshot}
        now={now}
        sound={alerts.sound}
        onSound={alerts.chooseSound}
        onTop={onTop}
        onOnTop={chooseOnTop}
      />
      {notice ? (
        <div className="top-nine-notice" role="alert" data-testid="top-nine-notice">{notice}</div>
      ) : null}
      <div className="top-nine-grid">
        {empty ? (
          <div className="top-nine-empty" role="status" data-testid="top-nine-empty">{empty}</div>
        ) : (
          <>
            {rows.map((row) => (
              <TopNineTile
                key={row.symbol}
                ref={refFor(row.symbol)}
                row={row}
                move={marks.marks[row.symbol]}
                endTime={endTime}
                now={now}
                opening={opening === row.symbol}
                muted={alerts.muted.has(row.symbol)}
                onOpen={openInTrader}
                onMenu={openMenu}
              />
            ))}
            {Array.from({ length: Math.max(0, TOP_NINE_SIZE - rows.length) }, (_, i) => (
              <div key={`slot-${i}`} className="top-nine-tile is-vacant" aria-hidden="true" />
            ))}
          </>
        )}
      </div>
      <TopNineSwitchLog log={marks.log} onOpen={openInTrader} />
      {menu ? (
        <TopNineTileMenu
          at={menu}
          muted={alerts.muted.has(menu.symbol)}
          onToggle={alerts.toggleMute}
          onClose={closeMenu}
        />
      ) : null}
    </div>
  );
}
