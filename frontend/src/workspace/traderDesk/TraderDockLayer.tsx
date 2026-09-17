/**
 * Scanner-window drop well (ADR 011). Listens on window so the dashboard
 * stays clickable; overlay is paint-only.
 */
import { useEffect, useState } from 'react';
import { TRADER_DOCK_OVERLAY_LABEL } from '../../constantGroups/trader_view';
import { useWorkspace } from '../WorkspaceContext';
import { isForeignTabDrag } from './commands';
import { dataTransferHasTraderTab, readTraderTabDrag } from './protocol';
import './traderDockLayer.css';

export function TraderDockLayer() {
  const {
    traderTabs,
    traderViewActive,
    traderDockOffer,
    traderWindowId,
    acceptTraderTabDrop,
  } = useWorkspace();
  const [hover, setHover] = useState(false);
  const scannerIsDropSurface = traderTabs.length === 0 || !traderViewActive;

  useEffect(() => {
    if (!scannerIsDropSurface) {
      setHover(false);
      return undefined;
    }
    const onOver = (e: DragEvent) => {
      if (!e.dataTransfer || !dataTransferHasTraderTab(e.dataTransfer.types)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      setHover(true);
    };
    const onDrop = (e: DragEvent) => {
      setHover(false);
      if (!e.dataTransfer) return;
      const payload = readTraderTabDrag(e.dataTransfer);
      if (!payload || !isForeignTabDrag(payload.sourceWindowId, traderWindowId)) return;
      e.preventDefault();
      acceptTraderTabDrop(payload);
    };
    const onEnd = () => setHover(false);
    window.addEventListener('dragover', onOver);
    window.addEventListener('drop', onDrop);
    window.addEventListener('dragend', onEnd);
    return () => {
      window.removeEventListener('dragover', onOver);
      window.removeEventListener('drop', onDrop);
      window.removeEventListener('dragend', onEnd);
    };
  }, [acceptTraderTabDrop, scannerIsDropSurface, traderWindowId]);

  if (!scannerIsDropSurface) return null;

  const ready = hover || Boolean(
    traderDockOffer && isForeignTabDrag(traderDockOffer.sourceWindowId, traderWindowId),
  );
  if (!ready) return null;

  return (
    <div
      className="trader-dock-layer trader-dock-layer--ready"
      data-testid="trader-dock-layer"
      data-ready="1"
    >
      <p className="trader-dock-layer__label" role="status">
        {TRADER_DOCK_OVERLAY_LABEL}
        {traderDockOffer ? ` (${traderDockOffer.symbol})` : ''}
      </p>
    </div>
  );
}
