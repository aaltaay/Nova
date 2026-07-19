/**
 * Versioned workspace layout — slot → ordered module ids (+ optional sizes).
 * Persisted in localStorage (Phase 5). Drag-drop writes here via reorderModulesInSlot (Phase 6).
 */
import { LAYOUT_SCHEMA_VERSION, LAYOUT_STORAGE_KEY } from '../constants';

export type LayoutSlotId = 'side_panel' | 'stock_view';

export type LayoutSlots = Record<LayoutSlotId, string[]>;

export type WorkspaceLayout = {
  version: number;
  slots: LayoutSlots;
  /** Optional per-module size hints (unused until Phase 6 resize). */
  sizes?: Record<string, number>;
};

/** Modules that may appear in quote-panel layout order (both slots). */
export const QUOTE_LAYOUT_MODULE_IDS = [
  'quote',
  'level2',
  'tape',
  'news',
  'charts',
] as const;

export type QuoteLayoutModuleId = (typeof QUOTE_LAYOUT_MODULE_IDS)[number];

/** Columns-style default: chart → L2/T&S → news → quote (matches pre-Phase-5 UI). */
export function defaultSidePanelOrder(): string[] {
  return ['charts', 'level2', 'tape', 'news', 'quote'];
}

/** Stock View quote column default (no embedded panel chart — ChartGrid is separate).
 * News is rendered in the Stock View page footer; order entry still lists it for Modules. */
export function defaultStockViewOrder(): string[] {
  return ['level2', 'tape', 'quote', 'news', 'charts'];
}

export function defaultLayout(): WorkspaceLayout {
  return {
    version: LAYOUT_SCHEMA_VERSION,
    slots: {
      side_panel: defaultSidePanelOrder(),
      stock_view: defaultStockViewOrder(),
    },
    sizes: {},
  };
}

function isLayoutSlotId(id: string): id is LayoutSlotId {
  return id === 'side_panel' || id === 'stock_view';
}

function sanitizeOrder(ids: unknown, fallback: string[]): string[] {
  if (!Array.isArray(ids)) return [...fallback];
  const allowed = new Set<string>(QUOTE_LAYOUT_MODULE_IDS);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of ids) {
    if (typeof raw !== 'string' || !allowed.has(raw) || seen.has(raw)) continue;
    seen.add(raw);
    out.push(raw);
  }
  for (const id of fallback) {
    if (!seen.has(id)) out.push(id);
  }
  return out;
}

/**
 * Normalize any stored / partial layout into the current schema.
 * Unknown versions and corrupt payloads fall back to defaults (with salvage when possible).
 */
export function migrateLayout(raw: unknown): WorkspaceLayout {
  const defaults = defaultLayout();
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return defaults;

  const obj = raw as Record<string, unknown>;
  const version = typeof obj.version === 'number' ? obj.version : 0;

  // Future majors: add step-wise migrations here. Unknown/newer → defaults.
  if (version > LAYOUT_SCHEMA_VERSION) return defaults;

  const slotsRaw =
    obj.slots && typeof obj.slots === 'object' && !Array.isArray(obj.slots)
      ? (obj.slots as Record<string, unknown>)
      : {};

  const slots: LayoutSlots = {
    side_panel: sanitizeOrder(slotsRaw.side_panel, defaults.slots.side_panel),
    stock_view: sanitizeOrder(slotsRaw.stock_view, defaults.slots.stock_view),
  };

  let sizes: Record<string, number> | undefined;
  if (obj.sizes && typeof obj.sizes === 'object' && !Array.isArray(obj.sizes)) {
    sizes = {};
    for (const [k, v] of Object.entries(obj.sizes as Record<string, unknown>)) {
      if (typeof v === 'number' && Number.isFinite(v) && v > 0) sizes[k] = v;
    }
  }

  return {
    version: LAYOUT_SCHEMA_VERSION,
    slots,
    sizes: sizes ?? {},
  };
}

export function parseLayout(raw: string | null): WorkspaceLayout {
  if (!raw) return defaultLayout();
  try {
    return migrateLayout(JSON.parse(raw) as unknown);
  } catch {
    return defaultLayout();
  }
}

export function loadLayout(
  storage: Pick<Storage, 'getItem'> = localStorage,
): WorkspaceLayout {
  try {
    return parseLayout(storage.getItem(LAYOUT_STORAGE_KEY));
  } catch {
    return defaultLayout();
  }
}

export function saveLayout(
  layout: WorkspaceLayout,
  storage: Pick<Storage, 'setItem'> = localStorage,
): void {
  try {
    const normalized = migrateLayout(layout);
    storage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(normalized));
  } catch {
    /* quota / private mode — ignore */
  }
}

export function resetLayout(
  storage: Pick<Storage, 'setItem' | 'removeItem'> = localStorage,
): WorkspaceLayout {
  const next = defaultLayout();
  try {
    storage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(next));
  } catch {
    try {
      storage.removeItem(LAYOUT_STORAGE_KEY);
    } catch {
      /* ignore */
    }
  }
  return next;
}

export function getSlotOrder(layout: WorkspaceLayout, slot: LayoutSlotId): string[] {
  return layout.slots[slot] ?? defaultLayout().slots[slot];
}

/** Move a module one step within a slot. Returns a new layout (or same if no-op). */
export function moveModuleInSlot(
  layout: WorkspaceLayout,
  slot: LayoutSlotId,
  moduleId: string,
  direction: 'up' | 'down',
): WorkspaceLayout {
  const order = [...getSlotOrder(layout, slot)];
  const idx = order.indexOf(moduleId);
  if (idx < 0) return layout;
  const target = direction === 'up' ? idx - 1 : idx + 1;
  if (target < 0 || target >= order.length) return layout;
  const swap = order[target]!;
  order[target] = order[idx]!;
  order[idx] = swap;
  return {
    ...layout,
    version: LAYOUT_SCHEMA_VERSION,
    slots: { ...layout.slots, [slot]: order },
  };
}

/**
 * Reorder by dragging `activeId` onto `overId` within a slot (Phase 6 dnd-kit).
 * Returns the same layout reference when the move is a no-op.
 */
export function reorderModulesInSlot(
  layout: WorkspaceLayout,
  slot: LayoutSlotId,
  activeId: string,
  overId: string,
): WorkspaceLayout {
  if (activeId === overId) return layout;
  const order = [...getSlotOrder(layout, slot)];
  const oldIndex = order.indexOf(activeId);
  const newIndex = order.indexOf(overId);
  if (oldIndex < 0 || newIndex < 0 || oldIndex === newIndex) return layout;
  const [item] = order.splice(oldIndex, 1);
  order.splice(newIndex, 0, item!);
  return {
    ...layout,
    version: LAYOUT_SCHEMA_VERSION,
    slots: { ...layout.slots, [slot]: order },
  };
}

export function isLayoutSlot(id: string): id is LayoutSlotId {
  return isLayoutSlotId(id);
}

/** Collapse level2 + tape into one depth_tape block (first occurrence wins). */
export function coalesceQuoteOrder(order: string[]): string[] {
  const out: string[] = [];
  let depthPlaced = false;
  for (const id of order) {
    if (id === 'level2' || id === 'tape') {
      if (depthPlaced) continue;
      depthPlaced = true;
      out.push('depth_tape');
      continue;
    }
    out.push(id);
  }
  return out;
}
