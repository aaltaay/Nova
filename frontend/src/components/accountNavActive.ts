/**
 * Broadcast whether Scanner Account (trading/reports) tab is showing
 * so GlobalAppBar can highlight the Account control.
 */
const EVENT = 'nova:account-nav-active';

let active = false;

export function setAccountNavActive(next: boolean): void {
  if (active === next) return;
  active = next;
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(EVENT, { detail: { active } }));
}

export function getAccountNavActive(): boolean {
  return active;
}

export function subscribeAccountNavActive(
  listener: (active: boolean) => void,
): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const on = (e: Event) => {
    const detail = (e as CustomEvent<{ active: boolean }>).detail;
    listener(Boolean(detail?.active));
  };
  window.addEventListener(EVENT, on);
  return () => window.removeEventListener(EVENT, on);
}
