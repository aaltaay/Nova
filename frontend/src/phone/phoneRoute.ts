/**
 * Where the phone is: one screen at a time, named in the page's hash so the phone's own Back
 * gesture walks the screens. Pure, apart from the two helpers that touch `window`.
 */

export type PhoneTab = 'scan' | 'trade' | 'home' | 'top9' | 'account';

export type PhoneRoute =
  | { screen: 'home' }
  | { screen: 'scan' }
  | { screen: 'top9' }
  | { screen: 'account' }
  | { screen: 'settings' }
  | { screen: 'trade'; symbol: string | null }
  | { screen: 'stock'; symbol: string }
  | { screen: 'chart'; symbol: string };

export const HOME: PhoneRoute = { screen: 'home' };

const SYMBOL = /^[A-Z0-9.-]{1,16}$/;

/** A ticker as the desk writes it, or null when the text is not one. */
export function cleanSymbol(raw: string | null | undefined): string | null {
  const text = (raw ?? '').trim().toUpperCase();
  return SYMBOL.test(text) ? text : null;
}

/** The route a hash names. Anything unknown is Home: a stale link never shows a blank page. */
export function parseRoute(hash: string): PhoneRoute {
  const [head, tail] = hash.replace(/^#\/?/, '').split('/');
  const symbol = cleanSymbol(tail ? decodeURIComponent(tail) : null);
  switch (head) {
    case 'scan':
    case 'top9':
    case 'account':
    case 'settings':
      return { screen: head };
    case 'trade':
      return { screen: 'trade', symbol };
    case 'stock':
    case 'chart':
      return symbol ? { screen: head, symbol } : HOME;
    default:
      return HOME;
  }
}

export function routeHash(route: PhoneRoute): string {
  const symbol = 'symbol' in route && route.symbol ? `/${encodeURIComponent(route.symbol)}` : '';
  return `#/${route.screen}${symbol}`;
}

/** The bottom-bar tab a screen lights, or null for a screen reached from another (Stock, Settings, the big chart). */
export function tabOf(route: PhoneRoute): PhoneTab | null {
  switch (route.screen) {
    case 'home':
    case 'scan':
    case 'top9':
    case 'account':
    case 'trade':
      return route.screen;
    default:
      return null;
  }
}

/** Fired on `window` after `go` or `goBack` changed the route without a `popstate`. */
export const ROUTE_EVENT = 'nova-phone-route';

/** How many of our own steps sit behind this history entry: kept in the entry, so the phone's Back gesture counts too. */
function stepsBehind(): number {
  const state = window.history.state as { novaPhoneStep?: unknown } | null;
  return typeof state?.novaPhoneStep === 'number' ? state.novaPhoneStep : 0;
}

export function go(route: PhoneRoute): void {
  const hash = routeHash(route);
  if (window.location.hash === hash) return;
  window.history.pushState({ novaPhoneStep: stepsBehind() + 1 }, '', hash);
  window.dispatchEvent(new Event(ROUTE_EVENT));
}

/** One screen back; with nothing of ours behind (the page was opened here), to `fallback`. */
export function goBack(fallback: PhoneRoute): void {
  if (stepsBehind() > 0) {
    window.history.back();
    return;
  }
  window.history.replaceState({ novaPhoneStep: 0 }, '', routeHash(fallback));
  window.dispatchEvent(new Event(ROUTE_EVENT));
}
