/**
 * Compact Time & Sales tape -- newest print on top.
 * Owns useIbkrTape (same pattern as DepthLadder → useIbkrDepth).
 * Side is row tint only (no Side column): ask green | bid red | mid/unknown neutral.
 * DOM mounts a viewport window; the hook ring still holds TAPE_UI_MAX_ROWS.
 * Right-click opens a min-size display filter (does not change the tape stream).
 */
import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent, type UIEvent } from 'react';
import {
  TAPE_COL_HEADERS,
  TAPE_OVERSCAN_ROWS,
  TAPE_ROW_HEIGHT_PX,
  TAPE_SECTION_TITLE,
  TAPE_STICK_TOP_PX,
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
import { useIbkrTape, type TapePrint, type TapeSide } from './useIbkrTape';

interface Props {
  symbol: string | null;
  /** Parent rail: pane chrome + LIVE; no duplicate outer card title. */
  embedded?: boolean;
  /** False on live-but-hidden trader tabs -- ring stays hot, UI does not. */
  uiActive?: boolean;
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
      className={`ts-row ${sideClass(print.side)}`}
      style={{ height: TAPE_ROW_HEIGHT_PX }}
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
}: {
  badge: string | null;
  statusClass: string;
  statusText: string;
}) {
  return (
    <div className="ts-panel__header-end">
      {badge && (
        <span className="ts-panel__filter-badge" data-testid="ts-min-size-badge">
          {badge}
        </span>
      )}
      <span className={statusClass}>{statusText}</span>
    </div>
  );
}

export function TimeSalesPanel({ symbol, embedded = false, uiActive = true }: Props) {
  const { prints, connected, error } = useIbkrTape(symbol, uiActive);
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
    if (prints.length === 0) return 'Waiting for prints…';
    if (filtered.length === 0 && minSize > 0) return tapeMinSizeEmptyLabel(minSize);
    return null;
  }, [error, connected, prints.length, filtered.length, minSize]);

  const statusClass = `ts-panel__status ${connected ? 'ts-panel__status--live' : 'ts-panel__status--off'}`;
  const statusText = connected ? 'LIVE' : (error ? 'ERROR' : '…');
  const headMeta = (
    <TapeHeadMeta badge={badge} statusClass={statusClass} statusText={statusText} />
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
