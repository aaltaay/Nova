/**
 * Storage gate for the sample desk (#449) -- what sampleNetworkGate is to the
 * backend, this is to the operator's saved browser state.
 *
 * The sample desk mounts the live desk's own components -- the Trader's
 * splits and docks, the Focus rail, the chart grid, the hotkey store, the
 * watch list -- and each of them persists what is changed on it. Its own
 * workspace (SampleWorkspaceProvider) keeps tabs, the rail and the Desk in
 * memory, but guarding every other caller cannot be proven complete, so this
 * module is the backstop under all of them: one wrapper around
 * `Storage.prototype`, installed once in main.tsx before any app module
 * loads, that on the sample route
 *
 *   - keeps every `setItem` / `removeItem` / `clear` on `localStorage` and
 *     `sessionStorage` in a per-page, in-memory overlay -- nothing reaches the
 *     browser's storage;
 *   - answers `getItem` from that overlay first, then from the browser's
 *     storage, so the sample desk opens with the operator's theme and layout
 *     and simply never changes them.
 *
 * Off the sample route every call passes straight through. The decision is
 * made per call from the URL (sampleNav.isSampleView), like the network gate,
 * so entering or leaving the sample desk needs no re-install; the overlay
 * lives as long as the page. `key()` / `length` enumerate the browser's
 * storage only -- Nova enumerates storage only in tests.
 *
 * SAMPLE_STORAGE_PASSTHROUGH names the keys that must reach the browser: the
 * app shell's one-shot reload guard, which a reload would otherwise forget,
 * looping a sample page that fails on start.
 */
import { APP_SHELL_RELOAD_SESSION_KEY } from '../components/appErrorRecovery';
import { isSampleView } from './sampleNav';

/** Page mechanics, not the operator's state: they pass through on the sample route too. */
export const SAMPLE_STORAGE_PASSTHROUGH: ReadonlySet<string> = new Set([APP_SHELL_RELOAD_SESSION_KEY]);

/** Absorbed keys remembered for diagnostics and tests; the oldest fall off. */
const ABSORBED_LOG_MAX = 200;

type StorageMethods = Pick<Storage, 'getItem' | 'setItem' | 'removeItem' | 'clear'>;

interface Overlay {
  /** A key's sample value; null = removed on the sample desk. */
  values: Map<string, string | null>;
  /** `clear()` ran on the sample desk: keys not in `values` read as absent. */
  cleared: boolean;
}

interface Installed {
  proto: StorageMethods;
  native: StorageMethods;
}

let installed: Installed | null = null;
let overlays = new WeakMap<object, Overlay>();
const absorbed: string[] = [];

function overlayOf(store: object): Overlay {
  let overlay = overlays.get(store);
  if (!overlay) {
    overlay = { values: new Map(), cleared: false };
    overlays.set(store, overlay);
  }
  return overlay;
}

function remember(key: string): void {
  absorbed.push(key);
  if (absorbed.length > ABSORBED_LOG_MAX) absorbed.splice(0, absorbed.length - ABSORBED_LOG_MAX);
}

/** Keys the gate kept off the browser's storage since load (newest last). */
export function sampleStorageAbsorbed(): readonly string[] {
  return absorbed;
}

function gated(key: string, onSample: () => boolean): boolean {
  return onSample() && !SAMPLE_STORAGE_PASSTHROUGH.has(key);
}

/**
 * Wrap `proto`'s four mutating / reading methods once. Safe to call again (no
 * second wrapper); off the sample route the wrappers hand every call to the
 * originals unchanged.
 */
export function installSampleStorageGate(
  proto: StorageMethods | undefined = typeof Storage === 'undefined' ? undefined : Storage.prototype,
  onSample: () => boolean = () => isSampleView(),
): void {
  if (!proto || installed?.proto === proto) return;
  const native: StorageMethods = {
    getItem: proto.getItem,
    setItem: proto.setItem,
    removeItem: proto.removeItem,
    clear: proto.clear,
  };

  proto.getItem = function sampleGatedGetItem(this: Storage, key: string): string | null {
    const k = String(key);
    if (gated(k, onSample)) {
      const overlay = overlays.get(this);
      if (overlay?.values.has(k)) return overlay.values.get(k) ?? null;
      if (overlay?.cleared) return null;
    }
    return native.getItem.call(this, k);
  };

  proto.setItem = function sampleGatedSetItem(this: Storage, key: string, value: string): void {
    const k = String(key);
    if (gated(k, onSample)) {
      overlayOf(this).values.set(k, String(value));
      remember(k);
      return;
    }
    native.setItem.call(this, k, value);
  };

  proto.removeItem = function sampleGatedRemoveItem(this: Storage, key: string): void {
    const k = String(key);
    if (gated(k, onSample)) {
      overlayOf(this).values.set(k, null);
      remember(k);
      return;
    }
    native.removeItem.call(this, k);
  };

  proto.clear = function sampleGatedClear(this: Storage): void {
    if (onSample()) {
      const overlay = overlayOf(this);
      overlay.values.clear();
      overlay.cleared = true;
      remember('*');
      return;
    }
    native.clear.call(this);
  };

  installed = { proto, native };
}

/** Test helper: put the originals back and forget the overlay. */
export function uninstallSampleStorageGateForTests(): void {
  if (!installed) return;
  const { proto, native } = installed;
  proto.getItem = native.getItem;
  proto.setItem = native.setItem;
  proto.removeItem = native.removeItem;
  proto.clear = native.clear;
  installed = null;
  overlays = new WeakMap();
  absorbed.length = 0;
}
