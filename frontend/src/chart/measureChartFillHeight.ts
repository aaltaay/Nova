/** ADR 005 — chart layout helper for grid/maximized fill-parent sizing. */

/** Height for fill-parent charts: use card leftover space, not CHART_HEIGHT_GRID. */
export function measureChartFillHeight(container: HTMLElement, fallback: number): number {
  const card = container.closest('.chart-card') as HTMLElement | null;
  if (card && card.clientHeight > 0) {
    let used = 0;
    for (const child of Array.from(card.children)) {
      if (child === container) continue;
      used += (child as HTMLElement).offsetHeight;
    }
    const available = Math.floor(card.clientHeight - used);
    if (available > 0) return available;
  }
  return Math.max(container.clientHeight || fallback, fallback);
}
