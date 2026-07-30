/**
 * localStorage helpers for the AppShell HOD Momo / Running Up top dock.
 */
import {
  HOD_MOMO_DOCK_COLLAPSED_KEY,
  HOD_MOMO_DOCK_DEFAULT_COLLAPSED,
  HOD_MOMO_DOCK_DEFAULT_HEIGHT_PX,
  HOD_MOMO_DOCK_HEIGHT_KEY,
  HOD_MOMO_DOCK_MAX_HEIGHT_PX,
  HOD_MOMO_DOCK_MIN_HEIGHT_PX,
} from '../constants';

export function clampDockHeightPx(px: number): number {
  if (!Number.isFinite(px)) return HOD_MOMO_DOCK_DEFAULT_HEIGHT_PX;
  return Math.min(
    HOD_MOMO_DOCK_MAX_HEIGHT_PX,
    Math.max(HOD_MOMO_DOCK_MIN_HEIGHT_PX, Math.round(px)),
  );
}

export function readDockCollapsed(): boolean {
  try {
    const raw = localStorage.getItem(HOD_MOMO_DOCK_COLLAPSED_KEY);
    if (raw === '1') return true;
    if (raw === '0') return false;
  } catch {
    /* private mode */
  }
  return HOD_MOMO_DOCK_DEFAULT_COLLAPSED;
}

export function writeDockCollapsed(collapsed: boolean): void {
  try {
    localStorage.setItem(HOD_MOMO_DOCK_COLLAPSED_KEY, collapsed ? '1' : '0');
  } catch {
    /* ignore */
  }
}

export function readDockHeightPx(): number {
  try {
    const raw = localStorage.getItem(HOD_MOMO_DOCK_HEIGHT_KEY);
    const parsed = raw != null ? Number(raw) : NaN;
    if (Number.isFinite(parsed)) return clampDockHeightPx(parsed);
  } catch {
    /* ignore */
  }
  return HOD_MOMO_DOCK_DEFAULT_HEIGHT_PX;
}

export function writeDockHeightPx(heightPx: number): void {
  try {
    localStorage.setItem(
      HOD_MOMO_DOCK_HEIGHT_KEY,
      String(clampDockHeightPx(heightPx)),
    );
  } catch {
    /* ignore */
  }
}
