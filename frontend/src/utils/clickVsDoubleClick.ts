/**
 * Distinguish single vs double click without relying on native `dblclick`.
 * Native dblclick breaks when the first click re-renders or shifts layout
 * (Quote Panel selection) so the second click hits a different target.
 */

export type ClickVsDoubleClickHandlers = {
  /** Call from onClick / pointer up. */
  handleClick: () => void;
  /** Clear a pending single-click (unmount / symbol change). */
  cancel: () => void;
};

export function createClickVsDoubleClick(
  onSingle: () => void,
  onDouble: () => void,
  delayMs: number,
): ClickVsDoubleClickHandlers {
  let timer: ReturnType<typeof setTimeout> | null = null;

  return {
    handleClick: () => {
      if (timer != null) {
        clearTimeout(timer);
        timer = null;
        onDouble();
        return;
      }
      timer = setTimeout(() => {
        timer = null;
        onSingle();
      }, delayMs);
    },
    cancel: () => {
      if (timer != null) {
        clearTimeout(timer);
        timer = null;
      }
    },
  };
}
