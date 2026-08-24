/**
 * Merge IBKR *connection* keys into an existing desktop .env.
 * Never overwrites a key that is already set.
 * Never adds spend gates (orders / live confirm / short).
 */

export const IBKR_CONNECT_DEFAULTS = {
  IBKR_ENABLED: 'true',
  IBKR_HOST: '127.0.0.1',
  IBKR_PAPER_PORT: '4002',
  IBKR_LIVE_PORT: '4001',
};

export const IBKR_SPEND_KEYS = new Set([
  'IBKR_ORDERS_ENABLED',
  'IBKR_LIVE_TRADING_CONFIRMED',
  'IBKR_SHORT_ENABLED',
]);

export function parseEnvKeys(text) {
  const keys = new Set();
  for (const raw of String(text || '').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq <= 0) continue;
    keys.add(line.slice(0, eq).trim());
  }
  return keys;
}

export function mergeMissingEnvKeys(existingText, defaults = IBKR_CONNECT_DEFAULTS) {
  const text = String(existingText ?? '');
  const present = parseEnvKeys(text);
  const additions = [];
  for (const [key, value] of Object.entries(defaults)) {
    if (IBKR_SPEND_KEYS.has(key)) continue;
    if (present.has(key)) continue;
    additions.push(`${key}=${value}`);
  }
  if (additions.length === 0) return text;
  const body = text.endsWith('\n') || text.length === 0 ? text : `${text}\n`;
  return `${body}${additions.join('\n')}\n`;
}
