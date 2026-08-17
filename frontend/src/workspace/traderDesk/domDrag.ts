import type { DragEvent as ReactDragEvent } from 'react';
import { isForeignTabDrag } from './commands';
import {
  dataTransferHasTraderTab,
  readTraderTabDrag,
  writeTraderTabDrag,
  type TraderTabDragPayload,
} from './protocol';

export function allowTraderTabDrop(e: ReactDragEvent): boolean {
  if (!dataTransferHasTraderTab(e.dataTransfer.types)) return false;
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  return true;
}

export function startTraderTabDrag(
  e: ReactDragEvent,
  payload: { symbol: string; sourceWindowId: string },
): void {
  writeTraderTabDrag(e.dataTransfer, payload);
}

export function takeForeignTraderTabDrop(
  e: ReactDragEvent,
  thisWindowId: string,
): TraderTabDragPayload | null {
  e.preventDefault();
  const payload = readTraderTabDrag(e.dataTransfer);
  if (!payload || !isForeignTabDrag(payload.sourceWindowId, thisWindowId)) return null;
  return payload;
}
