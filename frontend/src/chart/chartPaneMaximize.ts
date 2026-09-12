/** When a Trader grid pane may toggle maximize from a double-click.

 * Armed drawing tools use pointerup place (D-010). A fast second click must
 * stay a place click, not a layout change. Buttons and resize handles keep
 * their own click / double-click contracts.
 */
const IGNORE_SELECTOR =
  'button, a, input, select, textarea, label, .resize-handle, [role="slider"]';

export function shouldToggleChartPaneMaximize(
  event: { target: EventTarget | null },
  activeTool: string | null,
): boolean {
  if (activeTool) return false;
  const target = event.target;
  if (!(target instanceof Element)) return false;
  return !target.closest(IGNORE_SELECTOR);
}
