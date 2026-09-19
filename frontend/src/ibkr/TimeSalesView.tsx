/**
 * Presentational Time & Sales tape -- newest print on top. Feed-agnostic:
 * TimeSalesPanel passes the live IBKR tape; historical replay passes the Sim
 * snapshot, so both render the same columns, rows and filter.
 * Side is row tint only (no Side column): ask green | bid red | mid/unknown neutral.
 * Unreported prints (IBKR tickAttribLast.unreported) are dimmed rows.
 * DOM mounts a viewport window; the feed ring still holds TAPE_UI_MAX_ROWS.
 * Right-click opens a min-size display filter (does not change the tape stream).
 */
import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent, type UIEvent } from 'react';
import {
  TAPE_COL_HEADERS,
  TAPE_EMPTY_LABEL,
  TAPE_OVERSCAN_ROWS,
  TAPE_ROW_HEIGHT_PX,
  TAPE_SECTION_TITLE,
  TAPE_STATUS_LIVE,
  TAPE_STICK_TOP_PX,
  TAPE_UNREPORTED_TITLE,
  TAPE_VIEWPORT_FALLBACK_ROWS,
} from '../constants';
import { createRafCoalesce } from '../utils/rafCoalesce';
import { TapeMinSizeFilterMenu } from './TapeMinSizeFilterMenu';
import {
  applyTapeMinSizeDraft,
  filterTapePrints,
  readTapeMinSize,
  tapeMinSizeBadgeLabel,
  tapeMinSizeEmptyLabel,
  writeTapeMinSize,
} from './tapeMinSizeFilter';
import {
  computeTapeVisibleRange,
  tapePinnedToNewest,
  tapeScrollAfterPrepend,
} from './tapeWindow';
import type { TapePrint, TapeSide, TapeState } from './tapeFeed';

export interface TimeSalesViewProps {
  symbol: string | null;
  feed: TapeState;
  /** Parent rail: pane chrome + LIVE; no duplicate outer card title. */
  embedded?: boolean;
  /** False on live-but-hidden trader tabs -- ring stays hot, UI does not. */
  uiActive?: boolean;
  /** Badge text while connected (default LIVE). */
  connectedText?: string;
  /** Badge tooltip, e.g. the replay data source. */
  statusTitle?: string;
  /** Empty-tape message while connected (default "Waiting for prints…"). */
  emptyLabel?: string;
}

function fmtTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return iso.slice(11, 19) || iso;
  }
}

function fmtPrice(p: number): string {
  return p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

function fmtSize(s: number): string {
  return s.toLocaleString('en-US');
}

function sideClass(side: TapeSide | undefined): string {
  switch (side) {
    case 'ask':
      return 'ts-row--ask';
    case 'bid':
      return 'ts-row--bid';
    case 'between':
      return 'ts-row--mid';
    default:
      return 'ts-row--unknown';
  }
}

function TapeRow({ print }: { print: TapePrint }) {
  return (
    <div
      className={`ts-row ${sideClass(print.side)}${print.unreported ? ' ts-row--unreported' : ''}`}
      style={{ height: TAPE_ROW_HEIGHT_PX }}
      title={print.unreported ? TAPE_UNREPORTED_TITLE : undefined}
      data-unreported={print.unreported ? '1' : undefined}
    >
      <span className="ts-col--time">{fmtTime(print.time)}</span>
      <span className="ts-col--price">{fmtPrice(print.price)}</span>
      <span className="ts-col--size" data-testid="ts-size" data-size={print.size}>
        {fmtSize(print.size)}
      </span>
      <span className="ts-col--exch">{print.exchange || '—'}</span>
    </div>
  );
}

function TapeHeadMeta({
  badge,
  statusClass,
  statusText,
  statusTitle,
}: {
  badge: string | null;
  statusClass: string;
  statusText: string;
  statusTitle?: string;
}) {
  return (
    <div className="ts-panel__header-end">
      {badge && (
        <span className="ts-panel__filter-badge" data-testid="ts-min-size-badge">
          {badge}
        </span>
      )}
      <span className={statusClass} title={statusTitle} data-testid="ts-status">{statusText}</span>
    </div>
  );
}

export function TimeSalesView({
  symbol,
  feed,
  embedded = false,
  uiActive = true,
  connectedText = TAPE_STATUS_LIVE,
  statusTitle,
  emptyLabel = TAPE_EMPTY_LABEL,
}: TimeSalesViewProps) {
  const { prints, connected, error } = feed;
  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportPx, setViewportPx] = useState(
    TAPE_VIEWPORT_FALLBACK_ROWS * TAPE_ROW_HEIGHT_PX,
  );
  const [minSize, setMinSize] = useState(() => readTapeMinSize());
  const [menu, setMenu] = useState<{ x: number; y: number; draft: string } | null>(null);
  const prevLenRef = useRef(0);
  const pinnedRef = useRef(true);
  const pendingScrollRef = useRef(0);
  const scrollRafRef = useRef(createRafCoalesce(() => {
    setScrollTop(pendingScrollRef.current);
  }));

  const filtered = useMemo(
    () => filterTapePrints(prints, minSize),
    [prints, minSize],
  );
  const badge = tapeMinSizeBadgeLabel(minSize);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(entries => {
      const h = entries[0]?.contentRect.height ?? 0;
      if (h > 0) setViewportPx(h);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    prevLenRef.current = 0;
    pinnedRef.current = true;
    setScrollTop(0);
    const el = scrollRef.current;
    if (el) el.scrollTop = 0;
  }, [symbol]);

  useEffect(() => {
    const el = scrollRef.current;
    const added = filtered.length - prevLenRef.current;
    prevLenRef.current = filtered.length;
    if (!el || added <= 0 || pinnedRef.current) return;
    const nextTop = tapeScrollAfterPrepend(
      el.scrollTop,
      added,
      TAPE_ROW_HEIGHT_PX,
      TAPE_STICK_TOP_PX,
    );
    el.scrollTop = nextTop;
    setScrollTop(nextTop);
  }, [filtered.length]);

  useEffect(() => {
    const raf = scrollRafRef.current;
    return () => raf.cancel();
  }, []);

  const onScroll = useCallback((event: UIEvent<HTMLDivElement>) => {
    const top = event.currentTarget.scrollTop;
    pinnedRef.current = tapePinnedToNewest(top);
    pendingScrollRef.current = top;
    scrollRafRef.current.schedule();
  }, []);

  const onContextMenu = useCallback((event: MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    setMenu({
      x: event.clientX,
      y: event.clientY,
      draft: minSize > 0 ? String(minSize) : '',
    });
  }, [minSize]);

  const onDraftChange = useCallback((next: string) => {
    setMenu((open) => (open ? { ...open, draft: next } : open));
    const parsed = applyTapeMinSizeDraft(next);
    if (parsed == null) return;
    setMinSize(parsed);
    writeTapeMinSize(parsed);
  }, []);

  const closeMenu = useCallback(() => setMenu(null), []);

  const range = computeTapeVisibleRange(
    scrollTop,
    filtered.length,
    TAPE_ROW_HEIGHT_PX,
    viewportPx,
    TAPE_OVERSCAN_ROWS,
  );
  const visible = filtered.slice(range.startIndex, range.endIndex);

  const statusLabel = useMemo(() => {
    if (error) return error;
    if (!connected) return 'Connecting…';
    if (prints.length === 0) return emptyLabel;
    if (filtered.length === 0 && minSize > 0) return tapeMinSizeEmptyLabel(minSize);
    return null;
  }, [error, connected, prints.length, filtered.length, minSize, emptyLabel]);

  const statusClass = `ts-panel__status ${connected ? 'ts-panel__status--live' : 'ts-panel__status--off'}`;
  const statusText = connected ? connectedText : (error ? 'ERROR' : '…');
  const headMeta = (
    <TapeHeadMeta
      badge={badge}
      statusClass={statusClass}
      statusText={statusText}
      statusTitle={statusTitle}
    />
  );

  const cols = (
    <div className="ts-panel__cols" data-testid="ts-panel-cols">
      <span className="ts-col--time">{TAPE_COL_HEADERS.time}</span>
      <span className="ts-col--price">{TAPE_COL_HEADERS.price}</span>
      <span className="ts-col--size">{TAPE_COL_HEADERS.size}</span>
      <span className="ts-col--exch">{TAPE_COL_HEADERS.exchange}</span>
    </div>
  );

  const rows = (
    <div
      className="ts-panel__rows"
      ref={scrollRef}
      onScroll={onScroll}
      data-testid="ts-panel-rows"
      data-ring-count={prints.length}
      data-filtered-count={filtered.length}
      data-min-size={minSize}
      data-rendered-count={statusLabel ? 0 : visible.length}
      data-tape-ui-active={uiActive ? '1' : '0'}
    >
      {statusLabel ? (
        <div className="ts-panel__empty">{statusLabel}</div>
      ) : (
        <>
          {range.topSpacerPx > 0 && <div style={{ height: range.topSpacerPx }} aria-hidden />}
          {visible.map((p, i) => (
            <TapeRow key={`${p.time}-${range.startIndex + i}`} print={p} />
          ))}
          {range.bottomSpacerPx > 0 && <div style={{ height: range.bottomSpacerPx }} aria-hidden />}
        </>
      )}
    </div>
  );

  const filterMenu = menu && (
    <TapeMinSizeFilterMenu
      x={menu.x}
      y={menu.y}
      draft={menu.draft}
      onDraftChange={onDraftChange}
      onClose={closeMenu}
    />
  );

  if (embedded) {
    return (
      <div
        className="sv-md-pane ts-panel ts-panel--embedded"
        data-testid="ts-panel"
        onContextMenu={onContextMenu}
      >
        <div className="sv-md-pane__head">
          <h3 className="sv-md-pane__title">{TAPE_SECTION_TITLE}</h3>
          {headMeta}
        </div>
        <div className="sv-md-pane__body">
          {cols}
          {rows}
        </div>
        {filterMenu}
      </div>
    );
  }

  return (
    <div className="ts-panel" data-testid="ts-panel" onContextMenu={onContextMenu}>
      <div className="ts-panel__header">
        <span className="ts-panel__title">{TAPE_SECTION_TITLE}</span>
        {headMeta}
      </div>
      {cols}
      {rows}
      {filterMenu}
    </div>
  );
}
