/**
 * The PC's clock, as this page knows it.
 *
 * On the desk the page and the backend share one machine, so the PC's clock is this page's own
 * (`Date.now()`), and the offset stays 0. On the phone (ADR 070) they do not: the backend stamps every
 * Level 2 frame on the PC's clock and judges an order's `action_wall_ms` against it, so a phone that
 * measured "how late did this frame arrive" or stamped an order on its own clock would be wrong by
 * however far the two clocks differ. The phone's heartbeat measures that difference and sets it here;
 * everything that compares a moment with the backend's reads `deskNow()`.
 */
let offsetMs = 0;

/** The PC's clock minus this device's, ms. The phone's heartbeat sets it; nothing on the desk does. */
export function setDeskClockOffsetMs(ms: number | null | undefined): void {
  offsetMs = typeof ms === 'number' && Number.isFinite(ms) ? ms : 0;
}

export function deskClockOffsetMs(): number {
  return offsetMs;
}

/** Now, on the PC's clock (epoch ms). */
export function deskNow(): number {
  return Date.now() + offsetMs;
}
