/**
 * @vitest-environment jsdom
 *
 * #449: on ?view=sample the operator's saved browser state is read, never
 * written -- every write lands in memory for the page's life; off the sample
 * route storage behaves as it always did.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { APP_SHELL_RELOAD_SESSION_KEY } from '../components/appErrorRecovery';
import {
  installSampleStorageGate,
  sampleStorageAbsorbed,
  uninstallSampleStorageGateForTests,
} from './sampleStorageGate';

const KEY = 'nova.trader.focusRail.v1';

function onRoute(path: string): void {
  window.history.replaceState({}, '', path);
}

beforeEach(() => {
  onRoute('/');
  localStorage.clear();
  sessionStorage.clear();
  localStorage.setItem(KEY, 'operator');
  installSampleStorageGate();
});

afterEach(() => {
  uninstallSampleStorageGateForTests();
  onRoute('/');
  localStorage.clear();
  sessionStorage.clear();
});

/** What the browser's storage holds, past the gate (re-installing forgets the overlay). */
function saved(store: Storage, key: string): string | null {
  uninstallSampleStorageGateForTests();
  try {
    return store.getItem(key);
  } finally {
    installSampleStorageGate();
  }
}

describe('sample storage gate', () => {
  it('keeps sample writes in memory: the page reads them, the browser never gets them', () => {
    onRoute('/?view=sample&symbol=SMPL');
    expect(localStorage.getItem(KEY)).toBe('operator');
    localStorage.setItem(KEY, 'sample');
    sessionStorage.setItem('nova.trader.tabs', '{"tabs":["SMPL"]}');
    expect(localStorage.getItem(KEY)).toBe('sample');
    expect(sessionStorage.getItem('nova.trader.tabs')).toBe('{"tabs":["SMPL"]}');
    expect(sampleStorageAbsorbed()).toEqual([KEY, 'nova.trader.tabs']);
    expect(saved(localStorage, KEY)).toBe('operator');
    expect(saved(sessionStorage, 'nova.trader.tabs')).toBeNull();
  });

  it('a sample remove or clear hides the key from the page and leaves it saved', () => {
    onRoute('/?view=sample');
    localStorage.removeItem(KEY);
    expect(localStorage.getItem(KEY)).toBeNull();
    localStorage.setItem('other', 'x');
    localStorage.clear();
    expect(localStorage.getItem('other')).toBeNull();
    expect(saved(localStorage, KEY)).toBe('operator');
  });

  it('the one-shot reload guard reaches the browser, so a failing sample page cannot loop', () => {
    onRoute('/?view=sample');
    sessionStorage.setItem(APP_SHELL_RELOAD_SESSION_KEY, '1');
    expect(saved(sessionStorage, APP_SHELL_RELOAD_SESSION_KEY)).toBe('1');
  });

  it('off the sample route every call passes through, and the live desk reads its own state again', () => {
    onRoute('/?view=sample');
    localStorage.setItem(KEY, 'sample');
    onRoute('/?view=stock&symbol=SMPL');
    expect(localStorage.getItem(KEY)).toBe('operator');
    localStorage.setItem(KEY, 'live');
    expect(saved(localStorage, KEY)).toBe('live');
  });

  it('installs once and uninstalls cleanly', () => {
    const wrapped = Storage.prototype.setItem;
    installSampleStorageGate();
    expect(Storage.prototype.setItem).toBe(wrapped);
    uninstallSampleStorageGateForTests();
    onRoute('/?view=sample');
    localStorage.setItem(KEY, 'unguarded');
    expect(localStorage.getItem(KEY)).toBe('unguarded');
  });
});
