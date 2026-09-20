/**
 * Local Vite serve only -- map repo NOVA_API_KEY onto VITE_NOVA_API_KEY, and
 * decide when that mapping is allowed to happen at all.
 */

/**
 * True only for a real `vite dev` server.
 *
 * Vitest resolves this same config with `command === 'serve'`, so the naive
 * `command === 'serve'` check injected the operator's real NOVA_API_KEY into
 * `import.meta.env` during tests (#293). novaFetch prefers an env key over
 * localStorage, so the localStorage test failed -- and printed the operator's
 * key in the assertion diff. A test run must not depend on whose machine it is.
 */
export function shouldInjectDevNovaApiKey(opts: {
  command: string;
  mode: string;
  /** `process.env.VITEST`, which Vitest sets for every test run. */
  vitest?: string;
}): boolean {
  if (opts.command !== 'serve') return false;
  if (opts.mode === 'test') return false;
  return !opts.vitest;
}

export function readDevNovaApiKey(env: Record<string, string | undefined>): string {
  const fromVite = (env.VITE_NOVA_API_KEY || '').trim();
  if (fromVite) return fromVite;
  return (env.NOVA_API_KEY || '').trim();
}
