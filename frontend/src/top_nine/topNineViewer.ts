/**
 * The pop-up's heartbeat: the desk window publishes the boards only while a Top 9 window is open,
 * so a desk with no pop-up writes nothing. The value is the pop-up's last beat (ms epoch).
 */
import { TOP_NINE_VIEWER_KEY, TOP_NINE_VIEWER_STALE_MS } from './topNineConstants';

export function beatTopNineViewer(now = Date.now(), storage: Pick<Storage, 'setItem'> = localStorage): void {
  try {
    storage.setItem(TOP_NINE_VIEWER_KEY, String(now));
  } catch {
    /* private mode: the desk falls back to not publishing, and the pop-up says it is waiting */
  }
}

export function topNineViewerAlive(now = Date.now(), storage: Pick<Storage, 'getItem'> = localStorage): boolean {
  try {
    const beat = Number(storage.getItem(TOP_NINE_VIEWER_KEY));
    return Number.isFinite(beat) && beat > 0 && now - beat < TOP_NINE_VIEWER_STALE_MS;
  } catch {
    return false;
  }
}
