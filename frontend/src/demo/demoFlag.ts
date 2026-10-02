/**
 * The demo build (ADR 043): `npm run build:demo` sets VITE_NOVA_DEMO=1. Every other build compiles
 * IS_DEMO to false, so the demo's modules (dynamic imports behind it) are never part of the desk.
 */
export const IS_DEMO = import.meta.env.VITE_NOVA_DEMO === '1';

/**
 * The demo's API origin. `.invalid` is reserved (RFC 2606) and never resolves, so a request aimed at
 * it that somehow escaped the page's transport would fail instead of reaching anything.
 */
export const DEMO_API_BASE = 'http://nova-demo.invalid';

/** Where the demo points people who want the real thing. */
export const DEMO_REPO_URL = 'https://github.com/aaltaay/Nova';
