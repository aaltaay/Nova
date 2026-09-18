/**
 * One callback per animation frame. Used by tape UI and chart store listeners
 * so a burst of AllLast prints becomes one React/paint commit.
 */
export interface RafCoalesce {
  schedule: () => void;
  flushNow: () => void;
  cancel: () => void;
  scheduled: () => boolean;
}

function scheduleFrame(cb: () => void): number {
  if (typeof requestAnimationFrame === 'function') {
    return requestAnimationFrame(cb);
  }
  return setTimeout(cb, 0) as unknown as number;
}

function cancelFrame(id: number): void {
  if (typeof cancelAnimationFrame === 'function') {
    cancelAnimationFrame(id);
    return;
  }
  clearTimeout(id);
}

export function createRafCoalesce(flush: () => void): RafCoalesce {
  let id: number | null = null;

  const cancel = () => {
    if (id == null) return;
    cancelFrame(id);
    id = null;
  };

  return {
    schedule() {
      if (id != null) return;
      id = scheduleFrame(() => {
        id = null;
        flush();
      });
    },
    flushNow() {
      cancel();
      flush();
    },
    cancel,
    scheduled: () => id != null,
  };
}
