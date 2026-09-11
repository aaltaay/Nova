/** Versioned localStorage helper (D-017). Missing version migrates; unknown refuses. */

export const PREF_SCHEMA_VERSION = 1;

type PrefEnvelope = {
  schema_version: number;
  value: unknown;
};

function isEnvelope(raw: unknown): raw is PrefEnvelope {
  return (
    !!raw &&
    typeof raw === 'object' &&
    !Array.isArray(raw) &&
    'schema_version' in raw &&
    'value' in raw
  );
}

export function readPref<T>(
  key: string,
  fallback: T,
  parse: (raw: unknown) => T | null,
  storage: Pick<Storage, 'getItem'> = localStorage,
): T {
  try {
    const raw = storage.getItem(key);
    if (raw == null) return fallback;
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      parsed = raw;
    }
    if (isEnvelope(parsed)) {
      if (Number(parsed.schema_version) !== PREF_SCHEMA_VERSION) return fallback;
      return parse(parsed.value) ?? fallback;
    }
    return parse(parsed) ?? fallback;
  } catch {
    return fallback;
  }
}

export function writePref(
  key: string,
  value: unknown,
  storage: Pick<Storage, 'setItem'> = localStorage,
): void {
  try {
    storage.setItem(
      key,
      JSON.stringify({ schema_version: PREF_SCHEMA_VERSION, value }),
    );
  } catch {
    /* private mode */
  }
}

export function parseBoolFlag(raw: unknown): boolean | null {
  if (raw === true || raw === 1 || raw === '1') return true;
  if (raw === false || raw === 0 || raw === '0') return false;
  return null;
}
