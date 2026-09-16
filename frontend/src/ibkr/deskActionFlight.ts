/**
 * Desk action in-flight latch -- Place / Flatten / Fill now.
 * Trading prerequisites must not auto-cover the ticket while this is set.
 */

let depth = 0;
const listeners = new Set<() => void>();

function notify(): void {
  for (const listener of [...listeners]) listener();
}

export function beginDeskAction(): () => void {
  depth += 1;
  notify();
  let released = false;
  return () => {
    if (released) return;
    released = true;
    depth = Math.max(0, depth - 1);
    notify();
  };
}

export function deskActionInFlight(): boolean {
  return depth > 0;
}

export function subscribeDeskAction(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function resetDeskActionForTests(): void {
  depth = 0;
  listeners.clear();
}
