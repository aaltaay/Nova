/**
 * Open / pin state for the header account cards -- Day's, Working, TAV and
 * the account pill (QA V15, 2026-09-22).
 *
 * Pointing at a trigger opens its card, and the click that follows used to
 * toggle that card straight back shut, so a mouse click looked dead. Now a
 * hover opens a card unpinned, and a click pins it; a click on a pinned card
 * closes it, and a click on a closed trigger opens its card pinned (the
 * keyboard's Enter is a click, so the keyboard toggles as before). Pure: the
 * cluster keeps the state, these decide the next one.
 */
export type ClusterMenu = 'day' | 'tav' | 'working' | 'pill';

export interface ClusterMenuState {
  open: ClusterMenu | null;
  /** True once a click (not a hover) holds the card open. */
  pinned: boolean;
}

export const CLUSTER_MENU_CLOSED: ClusterMenuState = { open: null, pinned: false };

/** The pointer entered `menu`'s trigger. */
export function clusterMenuOnHover(state: ClusterMenuState, menu: ClusterMenu): ClusterMenuState {
  if (state.open === menu) return state;
  return { open: menu, pinned: false };
}

/** `menu`'s trigger was clicked (mouse, touch or keyboard). */
export function clusterMenuOnClick(state: ClusterMenuState, menu: ClusterMenu): ClusterMenuState {
  if (state.open !== menu) return { open: menu, pinned: true };
  return state.pinned ? CLUSTER_MENU_CLOSED : { open: menu, pinned: true };
}
