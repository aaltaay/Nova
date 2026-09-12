/**
 * Binds the right-click gesture on one chart pane's `.chart-body` and portals
 * the menu to `document.body` so it is never clipped by the pane.
 *
 * Listens natively (not via React `onContextMenu`) because the LWC canvas owns
 * the pointer stack; the ignore selector in `shouldOpenChartContextMenu` keeps
 * the Long/Short tag's own menu the only one that opens on the badge.
 */
import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { defaultTicketQty } from '../ibkr/applyTicketDefaults';
import { ChartContextMenu } from './ChartContextMenu';
import { shouldOpenChartContextMenu } from './chartContextMenuItems';
import { stageChartOrder, type ChartOrderIntent } from './chartOrderActions';
import { placePointFromPointer } from './chartDrawingPlace';
import { downloadChartSnapshot } from './chartSnapshot';
import { resetChartViewport } from './chartViewportReset';
import { useChartPositionContext } from './useChartPositionContext';

interface OpenState {
  x: number;
  y: number;
  price: number | null;
}

export function ChartContextMenuHost(props: {
  symbol: string;
  timeframe: string;
  barCount: number;
  chart: IChartApi | null;
  candleSeriesRef: RefObject<ISeriesApi<'Candlestick'> | null>;
  containerRef: RefObject<HTMLElement | null>;
  activeTool: string | null;
  onToolClick: (toolId: string) => void;
}) {
  const [open, setOpen] = useState<OpenState | null>(null);
  const rootRef = useRef<HTMLElement | null>(null);
  const positionCtx = useChartPositionContext(props.symbol);
  const dismiss = useCallback(() => setOpen(null), []);

  const { containerRef, candleSeriesRef } = props;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const onContextMenu = (event: globalThis.MouseEvent) => {
      if (!shouldOpenChartContextMenu(event.target)) return;
      event.preventDefault();
      const point = placePointFromPointer(container, event.clientX, event.clientY);
      const coordPrice = candleSeriesRef.current?.coordinateToPrice(point.y);
      setOpen({
        x: event.clientX,
        y: event.clientY,
        price: typeof coordPrice === 'number' ? coordPrice : null,
      });
    };
    container.addEventListener('contextmenu', onContextMenu);
    return () => container.removeEventListener('contextmenu', onContextMenu);
  }, [containerRef, candleSeriesRef]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: globalThis.PointerEvent) => {
      const root = rootRef.current;
      if (root && root.contains(event.target as Node)) return;
      dismiss();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      // Beat useTickerChartEscape -- Escape closes this menu before it
      // disarms a drawing tool or leaves pane maximize.
      event.stopImmediatePropagation();
      dismiss();
    };
    document.addEventListener('pointerdown', onPointerDown, true);
    window.addEventListener('keydown', onKeyDown, true);
    window.addEventListener('resize', dismiss);
    window.addEventListener('blur', dismiss);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown, true);
      window.removeEventListener('keydown', onKeyDown, true);
      window.removeEventListener('resize', dismiss);
      window.removeEventListener('blur', dismiss);
    };
  }, [open, dismiss]);

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div ref={rootRef as RefObject<HTMLDivElement>} className="chart-context-menu-layer">
      <ChartContextMenu
        symbol={props.symbol}
        price={open.price}
        quantityValue={defaultTicketQty()}
        anchor={{ x: open.x, y: open.y }}
        position={positionCtx.position}
        mode={positionCtx.mode}
        connected={positionCtx.connected}
        spendStatus={positionCtx.spendStatus}
        flattenDisabled={positionCtx.flattenDisabled}
        activeTool={props.activeTool}
        onStageOrder={(intent: ChartOrderIntent) => {
          if (open.price == null) return;
          stageChartOrder({ symbol: props.symbol, intent, price: open.price });
        }}
        onToolClick={props.onToolClick}
        onReset={() => resetChartViewport(props.chart, props.timeframe, props.barCount)}
        onSnapshot={() =>
          downloadChartSnapshot(props.chart, props.symbol, props.timeframe)
        }
        onDismiss={dismiss}
      />
    </div>,
    document.body,
  );
}
