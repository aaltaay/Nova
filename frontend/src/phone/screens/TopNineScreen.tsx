/**
 * Top 9 (frozen mockup R2-Grid): the desk's Top 9, nine 1-minute charts on one screen.
 *
 * Everything the desk's pop-up does, it does here by the same code: the first nine rows of Gappers,
 * Gainers or After Hours as the scanner serves them; a stock that changes rank lights green (up),
 * red (down) or blue (new) for 30 seconds with a bar running out along its top edge, then keeps a
 * soft tint on its rank; a halt is flagged; Gainers draws the LULD band; a switch chimes at most
 * once in 30 seconds. Tap a tile for the stock page, the blue chip for the Trader.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Bell, BellOff } from 'lucide-react';
import { useLiveScannerFeed } from '../../scanner/ScannerDataContext';
import { chimeWorthy } from '../../top_nine/topNineAlerts';
import {
  TOP_NINE_AFTER_HOURS_EMPTY,
  TOP_NINE_CHIME_COOLDOWN_MS,
  TOP_NINE_LIST_EMPTY,
  TOP_NINE_LISTS,
  TOP_NINE_LULD_LISTS,
  TOP_NINE_SIZE,
  type TopNineList,
} from '../../top_nine/topNineConstants';
import { markLeft, markPhase, moveText, type TopNineMove, type TopNineSwitch } from '../../top_nine/topNineMarks';
import { readTopNineList, writeTopNineList } from '../../top_nine/topNineNav';
import type { TopNineRow } from '../../top_nine/topNineSnapshot';
import { useTopNineAlerts } from '../../top_nine/useTopNineAlerts';
import { etChartSeconds } from '../../tickerChartData';
import { LinkPill, PadlockButton, PhoneScreen, RowLink, TickerChip, VenuePill } from '../PhoneChrome';
import { compact, pct1, toneOf } from '../phoneFormat';
import { usePhoneTopNine } from '../usePhoneTopNine';
import { TopNineTileChart } from './TopNineTileChart';
import './topNine.css';

/** How many of the newest switches the bottom line has room for. */
const LOG_CHIPS = 3;
const BUZZ_MS = 60;

function useNow(ms: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(timer);
  }, [ms]);
  return now;
}

/** `▲ 5→4`, `▼ 4→5`, `NEW`: the desk's words, without the spaces a tile has no room for. */
function pillText(move: TopNineMove): string {
  const arrow = move.kind === 'up' ? '▲ ' : move.kind === 'down' ? '▼ ' : '';
  return `${arrow}${moveText(move).replace(/ /g, '')}`;
}

function Tile({ row, move, endTime, luld, now }: {
  row: TopNineRow; move: TopNineMove | undefined; endTime: number | null; luld: boolean; now: number;
}) {
  const phase = markPhase(move, now);
  const kind = phase === 'none' ? null : move?.kind ?? null;
  const tone = toneOf(row.changePct == null ? null : row.changePct * 100, 1);
  return (
    <div
      className="ph-t9tile"
      data-testid={`phone-top9-tile-${row.symbol}`}
      data-rank={row.rank}
      data-mark={kind ?? 'none'}
      data-phase={phase}
      data-halted={row.halted ? 'true' : undefined}
    >
      {phase === 'full' && move ? (
        <>
          {/* Keyed by the moment of the switch, so a second switch flashes again. */}
          <i key={move.at} className="ph-t9tile__flash" aria-hidden="true" />
          <i className="ph-t9tile__timer" aria-hidden="true">
            <b style={{ transform: `scaleX(${markLeft(move, now).toFixed(3)})` }} />
          </i>
        </>
      ) : null}
      <div className="ph-t9tile__head">
        <span className="ph-t9tile__rank">{row.rank}</span>
        <TickerChip symbol={row.symbol} small />
      </div>
      <div className="ph-t9tile__line">
        <span className="ph-t9tile__chg" data-tone={tone || 'flat'}>{pct1(row.changePct)}</span>
        {phase === 'full' && move ? (
          <span className="ph-t9tile__pill" data-testid={`phone-top9-pill-${row.symbol}`}>{pillText(move)}</span>
        ) : row.halted ? (
          <span className="ph-t9tile__halt">HALT</span>
        ) : null}
      </div>
      <TopNineTileChart symbol={row.symbol} lastPrice={row.price} endTime={endTime} luld={luld} />
      <div className="ph-t9tile__foot">
        <span>Vol <b>{compact(row.volume)}</b></span>
        <span>Float <b>{compact(row.float)}</b></span>
      </div>
      <RowLink symbol={row.symbol} />
    </div>
  );
}

interface LogChip {
  key: string;
  symbol: string;
  text: string;
  kind: 'up' | 'down' | 'new' | 'out';
}

/** The newest switches first: each stock that moved, and each that dropped out of the nine. */
function logChips(log: readonly TopNineSwitch[]): LogChip[] {
  const chips: LogChip[] = [];
  for (const entry of log) {
    for (const move of entry.moves) {
      chips.push({ key: `${entry.at}-${move.symbol}`, symbol: move.symbol, kind: move.kind, text: move.kind === 'new' ? 'new' : pillText(move) });
    }
    for (const symbol of entry.left) chips.push({ key: `${entry.at}-${symbol}-out`, symbol, kind: 'out', text: 'out' });
    if (chips.length >= LOG_CHIPS) break;
  }
  return chips.slice(0, LOG_CHIPS);
}

export function TopNineScreen() {
  const feed = useLiveScannerFeed();
  const [list, setListState] = useState<TopNineList>(() => readTopNineList());
  const listRef = useRef(list);
  listRef.current = list;
  const lastBuzz = useRef(0);

  // The feed calls back on a switch; the sound hook, below it, answers.
  const onSwitchRef = useRef<(l: TopNineList, s: TopNineSwitch) => void>(() => undefined);
  const top = usePhoneTopNine(feed, (switchedList, switched) => onSwitchRef.current(switchedList, switched));
  const alerts = useTopNineAlerts(list, top.snapshot);
  onSwitchRef.current = (switchedList, switched) => {
    alerts.onSwitch(switchedList, switched);
    // The buzz follows the chime's own rule: the list on screen, a stock that moved up or came in, the same pause.
    const now = Date.now();
    if (alerts.sound && switchedList === listRef.current && chimeWorthy(switched, alerts.muted)
      && now - lastBuzz.current >= TOP_NINE_CHIME_COOLDOWN_MS) {
      lastBuzz.current = now;
      navigator.vibrate?.(BUZZ_MS);
    }
  };
  const now = useNow(1_000);

  // The list on screen is the one whose prices the desk's Level 1 budget keeps moving.
  const { setL1ActiveTab } = feed;
  useEffect(() => {
    setL1ActiveTab(list);
  }, [list, setL1ActiveTab]);

  const chooseList = useCallback((next: TopNineList) => {
    writeTopNineList(next);
    setListState(next);
  }, []);

  const snapshot = top.snapshot;
  const rows = snapshot?.lists[list].rows ?? [];
  const marks = top.marks[list];
  const endTime = snapshot ? etChartSeconds(snapshot.asOf * 1000) : null;
  const luld = TOP_NINE_LULD_LISTS.includes(list);
  const label = TOP_NINE_LISTS.find((l) => l.list === list)?.label ?? list;

  let empty: string | null = null;
  if (!snapshot) empty = 'Reading the scanner…';
  else if (snapshot.source.kind === 'unknown') empty = snapshot.source.why;
  else if (!rows.length) empty = list === 'afterhours' ? TOP_NINE_AFTER_HOURS_EMPTY : TOP_NINE_LIST_EMPTY(label);

  const chips = logChips(marks.log);
  return (
    <PhoneScreen
      name="top9"
      tab="top9"
      header={(
        <div className="ph-head">
          <VenuePill />
          <div className="ph-head__title">Top 9</div>
          <div className="ph-grow" />
          <button
            type="button"
            className="ph-t9bell"
            aria-pressed={alerts.sound}
            aria-label={alerts.sound ? 'Sound and buzz on a switch: on' : 'Sound and buzz on a switch: off'}
            data-testid="phone-top9-sound"
            onClick={() => alerts.chooseSound(!alerts.sound)}
          >
            {alerts.sound ? <Bell size={16} aria-hidden="true" /> : <BellOff size={16} aria-hidden="true" />}
          </button>
          <LinkPill live />
          <PadlockButton />
        </div>
      )}
    >
      <div className="ph-undertabs ph-t9tabs">
        {TOP_NINE_LISTS.map((l) => (
          <button key={l.list} type="button" aria-pressed={l.list === list} onClick={() => chooseList(l.list)}>
            {l.label}
            <span className="ph-count">{snapshot?.lists[l.list].total ?? 0}</span>
          </button>
        ))}
      </div>
      {empty ? <div className="ph-empty" role="status" data-testid="phone-top9-empty">{empty}</div> : (
        <div className="ph-t9grid" data-testid="phone-top9-grid">
          {rows.map((row) => (
            <Tile key={row.symbol} row={row} move={marks.marks[row.symbol]} endTime={endTime} luld={luld} now={now} />
          ))}
          {Array.from({ length: Math.max(0, TOP_NINE_SIZE - rows.length) }, (_, i) => (
            <div key={`slot-${i}`} className="ph-t9tile is-vacant" aria-hidden="true" />
          ))}
        </div>
      )}
      <div className="ph-t9log" data-testid="phone-top9-log">
        <span className="ph-t9log__label">Switches</span>
        {chips.length ? chips.map((c) => (
          <span key={c.key} className="ph-t9log__chip" data-kind={c.kind}><b>{c.symbol}</b> {c.text}</span>
        )) : <span className="ph-faint">None yet</span>}
      </div>
    </PhoneScreen>
  );
}
