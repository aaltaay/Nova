/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { PREF_SCHEMA_VERSION, parseBoolFlag, readPref, writePref } from './prefStore';

describe('prefStore', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('writes a schema_version envelope', () => {
    writePref('nova.test.pref', ['NYSE']);
    const stored = JSON.parse(localStorage.getItem('nova.test.pref') ?? '');
    expect(stored.schema_version).toBe(PREF_SCHEMA_VERSION);
    expect(stored.value).toEqual(['NYSE']);
  });

  it('migrates a legacy raw array', () => {
    localStorage.setItem('nova.test.pref', JSON.stringify(['NASDAQ']));
    const value = readPref('nova.test.pref', [], (raw) =>
      Array.isArray(raw) && raw.every((x) => typeof x === 'string') ? raw : null,
    );
    expect(value).toEqual(['NASDAQ']);
  });

  it('migrates a legacy 0/1 flag', () => {
    localStorage.setItem('nova.test.flag', '0');
    expect(readPref('nova.test.flag', true, parseBoolFlag)).toBe(false);
  });

  it('refuses an unknown schema_version', () => {
    localStorage.setItem(
      'nova.test.pref',
      JSON.stringify({ schema_version: 99, value: ['NOPE'] }),
    );
    const value = readPref('nova.test.pref', ['SAFE'], (raw) =>
      Array.isArray(raw) ? (raw as string[]) : null,
    );
    expect(value).toEqual(['SAFE']);
  });
});
