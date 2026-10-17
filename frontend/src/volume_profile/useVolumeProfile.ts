/**
 * Today's and yesterday's volume profiles on one 5-minute pane (plan §6): the primitive, the POC / VAH / VAL chips on
 * the price axis, room right of the last candle for today's lane, and the anchor the operator drags. The profiles come
 * from the backend (`volumeProfileApi.ts`); a drag snaps the anchor to a candle and reads today's profile again.
 */
import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type RefObject } from 'react';
import type { IChartApi, IPriceLine, ISeriesApi } from 'lightweight-charts';
import { afterPaintSettles, edgeContents, isFollowingRightEdge, operatorOwnsView, subscribeEdge } from '../chart';
import { etChartSeconds } from '../tickerChartData';
import type { VolumeProfile } from './volumeProfile';
import { fetchVolumeProfile, type ProfileAnswer, type ProfileKind } from './volumeProfileApi';
import { VolumeProfilePrimitive, type ProfileLayer } from './VolumeProfilePrimitive';
import {
  VP_COLORS,
  VP_DEFAULT_ANCHOR_MIN_ET,
  VP_EDGE_CHAR_PX,
  VP_EDGE_PAD_PX,
  VP_EDGE_RESERVE_MAX_PX,
  VP_HANDLE_HIT_PX,
  VP_LANE_GAP_PX,
  VP_LANE_MAX_PX,
  VP_LANE_SHARE,
  VP_RETRY_MS,
  VP_TODAY_REFRESH_MS,
  VP_YESTERDAY_TITLE,
  vpMissingNote,
  vpTodayTitle,
} from './volumeProfileConstants';

const DAY_SEC = 86_400;
const PREMARKET_START_SEC = 4 * 3600;

interface Options {
  symbol: string;
  chart: IChartApi | null;
  series: ISeriesApi<'Candlestick'> | null;
  containerRef: RefObject<HTMLElement | null>;
  barsRevision: number;
  enabled: boolean;
}

/** Chart seconds are Eastern wall time read as UTC; the backend speaks epoch seconds. */
function chartToEpoch(sec: number): number {
  return sec - (etChartSeconds(sec * 1000) - sec);
}

function clock(sec: number): string {
  const m = Math.floor((((sec % DAY_SEC) + DAY_SEC) % DAY_SEC) / 60);
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}

function lastBarTime(series: ISeriesApi<'Candlestick'>): number | null {
  const data = series.data();
  return data.length ? Number(data[data.length - 1].time) : null;
}

function layer(p: VolumeProfile, title: (start: number) => string): ProfileLayer {
  const start = etChartSeconds(p.from * 1000);
  return { profile: p, start, end: etChartSeconds(p.to * 1000), title: title(start) };
}

const NONE: ProfileAnswer = { profile: null, filling: false, error: null };

/** One profile from the backend; asked again while it is `filling`, else every `refreshMs` (0: never). */
function useProfile(
  kind: ProfileKind, symbol: string, enabled: boolean, day: string | null, anchorEpoch: number | null, refreshMs: number,
): ProfileAnswer {
  const [answer, setAnswer] = useState<ProfileAnswer>(NONE);
  useEffect(() => {
    setAnswer(NONE);
  }, [symbol, day]);
  useEffect(() => {
    if (!enabled || day == null || (kind === 'today' && anchorEpoch == null)) return undefined;
    const ctrl = new AbortController();
    let timer: ReturnType<typeof setTimeout> | null = null;
    const ask = () => {
      fetchVolumeProfile(symbol, kind, day, anchorEpoch, ctrl.signal)
        .then((next) => {
          setAnswer(next);
          const again = next.filling ? VP_RETRY_MS : refreshMs;
          if (again > 0 && !ctrl.signal.aborted) timer = setTimeout(ask, again);
        })
        .catch((err: unknown) => {
          if (ctrl.signal.aborted) return;
          console.warn(`Volume profile (${kind}) for ${symbol} failed:`, err);
          setAnswer({ profile: null, filling: false, error: 'the backend did not answer' });
        });
    };
    ask();
    return () => {
      ctrl.abort();
      if (timer) clearTimeout(timer);
    };
  }, [kind, symbol, enabled, day, anchorEpoch, refreshMs]);
  return answer;
}

/** The pane's last candle's ET date: the exchange day the pane calls today. */
function dayOf(chartSec: number): string {
  return new Date(Math.floor(chartSec / DAY_SEC) * DAY_SEC * 1000).toISOString().slice(0, 10);
}

export function useVolumeProfile({ symbol, chart, series, containerRef, barsRevision, enabled }: Options): void {
  const primitiveRef = useRef<VolumeProfilePrimitive | null>(null);
  /** Chart seconds of the anchor candle; null is 09:30 on the pane's last day. */
  const [anchor, setAnchor] = useState<number | null>(null);
  const last = enabled && series ? lastBarTime(series) : null;
  const dayStart = last == null ? null : Math.floor(last / DAY_SEC) * DAY_SEC;
  const anchorSec = anchor ?? (dayStart == null ? null : dayStart + VP_DEFAULT_ANCHOR_MIN_ET * 60);

  useEffect(() => setAnchor(null), [symbol]);

  const day = dayStart == null ? null : dayOf(dayStart);
  const todayAnswer = useProfile('today', symbol, enabled, day, anchorSec == null ? null : chartToEpoch(anchorSec),
    VP_TODAY_REFRESH_MS);
  const yesterdayAnswer = useProfile('yesterday', symbol, enabled, day, null, 0);
  const today = todayAnswer.profile;
  const yesterday = yesterdayAnswer.profile;
  const notes = [
    ...(today || !todayAnswer.error ? [] : [vpMissingNote("Today's", todayAnswer.error)]),
    ...(yesterday || !yesterdayAnswer.error ? [] : [vpMissingNote("Yesterday's", yesterdayAnswer.error)]),
  ];
  const notesKey = notes.join('\n');

  const edge = useSyncExternalStore(
    useCallback((onChange: () => void) => subscribeEdge(chart, onChange), [chart]),
    () => edgeContents(chart),
  );
  const longest = Math.max(0, ...edge.words.map((w) => w.text.length));
  const rightInset = longest ? Math.min(VP_EDGE_RESERVE_MAX_PX, longest * VP_EDGE_CHAR_PX + VP_EDGE_PAD_PX) : 0;

  useEffect(() => {
    if (!enabled || !chart || !series) return undefined;
    const primitive = new VolumeProfilePrimitive();
    series.attachPrimitive(primitive);
    primitiveRef.current = primitive;
    return () => {
      try {
        series.detachPrimitive(primitive);
      } catch {
        /* chart/series already gone */
      }
      if (primitiveRef.current === primitive) primitiveRef.current = null;
    };
  }, [enabled, chart, series]);

  useEffect(() => {
    const t = today ? layer(today, (s) => vpTodayTitle(clock(s))) : null;
    primitiveRef.current?.setScene({
      today: t ? { ...t, anchor: clock(t.start) } : null,
      yesterday: yesterday ? layer(yesterday, () => VP_YESTERDAY_TITLE) : null,
      rightInset,
      notes: notesKey ? notesKey.split('\n') : [],
    });
  }, [today, yesterday, rightInset, notesKey, enabled, chart, series]);

  // The levels' prices on the axis, the way every other line on the desk shows its price.
  useEffect(() => {
    if (!enabled || !series) return undefined;
    const lines: IPriceLine[] = [];
    const add = (price: number, color: string) =>
      lines.push(series.createPriceLine({ price, color, lineVisible: false, axisLabelVisible: true, title: '' }));
    if (yesterday) [yesterday.vah, yesterday.poc, yesterday.val].forEach((p) => add(p, VP_COLORS.yesterday));
    if (today) {
      add(today.vah, VP_COLORS.value);
      add(today.val, VP_COLORS.value);
      add(today.poc, VP_COLORS.poc);
    }
    return () => {
      for (const line of lines) {
        try {
          series.removePriceLine(line);
        } catch {
          /* series already gone */
        }
      }
    };
  }, [enabled, series, today, yesterday]);

  // Room for today's lane right of the last candle, only for a view that follows the live edge -- again whenever the
  // pane changes size (a maximize, the window), since the lane is a share of its width.
  const hasToday = !!today;
  useEffect(() => {
    if (!enabled || !chart || !series || !hasToday) return undefined;
    const ts = chart.timeScale();
    const makeRoom = () => {
      if (operatorOwnsView(chart)) return;
      const n = series.data().length;
      const range = ts.getVisibleLogicalRange();
      if (!range || !isFollowingRightEdge(range, n)) return;
      const lane = Math.min(VP_LANE_MAX_PX, ts.width() * VP_LANE_SHARE) + rightInset + VP_LANE_GAP_PX;
      const room = Math.ceil(lane / ts.options().barSpacing);
      if (range.to >= n - 1 + room) return;
      const shift = n - 1 + room - range.to;
      ts.setVisibleLogicalRange({ from: range.from + shift, to: range.to + shift });
    };
    let cancel = afterPaintSettles(makeRoom);
    const onSize = () => {
      cancel();
      cancel = afterPaintSettles(makeRoom);
    };
    ts.subscribeSizeChange(onSize);
    return () => {
      cancel();
      ts.unsubscribeSizeChange(onSize);
    };
  }, [enabled, chart, series, hasToday, rightInset, barsRevision]);

  // Drag the anchor's handle to any candle of the day; the profile follows the candle under the pointer.
  useEffect(() => {
    const el = containerRef.current;
    if (!enabled || !chart || !series || !el) return undefined;
    let dragging = false;
    let hovering = false;
    const local = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      return { x: e.clientX - r.left, y: e.clientY - r.top };
    };
    const onHandle = (x: number, y: number) => {
      const h = primitiveRef.current?.handle();
      const pad = VP_HANDLE_HIT_PX;
      return !!h && x >= h.x - pad && x <= h.x + h.w + pad && y >= h.y - pad && y <= h.y + h.h + pad;
    };
    const onDown = (e: PointerEvent) => {
      if (e.button !== 0) return;
      const { x, y } = local(e);
      if (!onHandle(x, y)) return;
      // Cancelling the press keeps it from the chart's pan and the drawing tools.
      e.preventDefault();
      e.stopPropagation();
      dragging = true;
      try {
        el.setPointerCapture(e.pointerId);
      } catch {
        /* the pointer is already up: the drag ends on its own pointerup */
      }
    };
    const onMove = (e: PointerEvent) => {
      const { x, y } = local(e);
      if (dragging) {
        e.stopPropagation();
        const t = primitiveRef.current?.timeAt(x);
        const lastT = lastBarTime(series);
        if (t == null || lastT == null) return;
        const open = Math.floor(lastT / DAY_SEC) * DAY_SEC + PREMARKET_START_SEC;
        if (t >= open && t <= lastT) setAnchor((prev) => (prev === t ? prev : t));
        return;
      }
      const over = onHandle(x, y);
      if (over !== hovering) {
        hovering = over;
        el.style.cursor = over ? 'ew-resize' : '';
      }
    };
    const onUp = (e: PointerEvent) => {
      if (!dragging) return;
      dragging = false;
      e.stopPropagation();
      if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
    };
    el.addEventListener('pointerdown', onDown, true);
    el.addEventListener('pointermove', onMove, true);
    el.addEventListener('pointerup', onUp, true);
    el.addEventListener('pointercancel', onUp, true);
    return () => {
      el.removeEventListener('pointerdown', onDown, true);
      el.removeEventListener('pointermove', onMove, true);
      el.removeEventListener('pointerup', onUp, true);
      el.removeEventListener('pointercancel', onUp, true);
      if (hovering) el.style.cursor = '';
    };
  }, [enabled, chart, series, containerRef]);
}
