/**
 * Merge IBKR *connection* keys into an existing desktop .env.
 * Never overwrites a key that is already set.
 * Never adds spend gates (orders / live confirm / short).
 */
import { randomBytes } from 'node:crypto';

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

export function readEnvValue(text, key) {
  const want = String(key || '').trim();
  if (!want) return '';
  for (const raw of String(text || '').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq <= 0) continue;
    if (line.slice(0, eq).trim() !== want) continue;
    let value = line.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"'))
      || (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    return value.trim();
  }
  return '';
}

/**
 * Same NOVA_API_KEY the API already uses (D-040). Do not invent a second
 * secret. Order: process env, NOVA_ENV_PATH file, repo .env (unpackaged /
 * portable), userData .env. Empty source='missing' means the caller may
 * generate once into the API's env file.
 */
export function pickNovaApiKey({
  processKey = '',
  envPathKey = '',
  repoKey = '',
  userDataKey = '',
  packaged = false,
} = {}) {
  const processTrim = String(processKey || '').trim();
  if (processTrim) return { key: processTrim, source: 'process' };
  const envPathTrim = String(envPathKey || '').trim();
  if (envPathTrim) return { key: envPathTrim, source: 'env_path' };
  const repoTrim = String(repoKey || '').trim();
  if (repoTrim && !packaged) return { key: repoTrim, source: 'repo' };
  const userTrim = String(userDataKey || '').trim();
  if (userTrim) return { key: userTrim, source: 'userdata' };
  if (repoTrim) return { key: repoTrim, source: 'repo' };
  return { key: '', source: 'missing' };
}


/** Env file the API should load -- same file that owns the picked key. */
export function pickNovaEnvPath({
  source = '',
  envPathOverride = '',
  repoEnv = '',
  userEnv = '',
  packaged = false,
} = {}) {
  if (source === 'env_path' && envPathOverride) return envPathOverride;
  if (source === 'repo' && repoEnv) return repoEnv;
  if (source === 'process') {
    return envPathOverride || (!packaged && repoEnv ? repoEnv : userEnv);
  }
  if ((source === 'generated' || source === 'missing') && !packaged && repoEnv) {
    return envPathOverride || repoEnv;
  }
  return envPathOverride || userEnv;
}


export function ensureNovaApiKey(existingText, generate) {
  const text = String(existingText ?? '');
  const current = readEnvValue(text, 'NOVA_API_KEY');
  if (current) {
    return { text, created: false, key: current };
  }
  const make = typeof generate === 'function' ? generate : defaultApiKey;
  const key = String(make() || '').trim();
  if (!key) {
    throw new Error('NOVA_API_KEY generator returned an empty value');
  }
  const body = text.endsWith('\n') || text.length === 0 ? text : `${text}\n`;
  return { text: `${body}NOVA_API_KEY=${key}\n`, created: true, key };
}

function defaultApiKey() {
  return randomBytes(24).toString('hex');
}
