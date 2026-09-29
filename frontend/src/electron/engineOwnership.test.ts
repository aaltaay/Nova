import path from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  ENGINE_OWNER_FILE,
  emptyPortPlan,
  engineHomeFromHealth,
  ownerRootFromEngine,
  ownerStartFailedPrompt,
  ownerUsable,
  readEngineOwner,
  sameRoot,
  writeEngineOwner,
} from '../../electron/engineOwnership.mjs';

const ROOT = 'C:\\Users\\op\\github\\Nova';
const WORKTREE = 'C:\\Users\\op\\github\\Nova\\.claude\\worktrees\\agent-1';
const USER_DATA = 'C:\\Users\\op\\AppData\\Roaming\\nova';

/** A checkout on disk: `.git` is a folder in a main checkout and a file in a worktree. */
function disk(root: string, { gitDir = true, env = true, start = true } = {}) {
  const files = new Set<string>();
  if (env) files.add(path.win32.join(root, '.env'));
  if (start) files.add(path.win32.join(root, 'scripts', 'Start-NovaApi.ps1'));
  if (!gitDir) files.add(path.win32.join(root, '.git'));
  return {
    exists: (p: string) => files.has(p) || (gitDir && p === path.win32.join(root, '.git')),
    isDir: (p: string) => gitDir && p === path.win32.join(root, '.git'),
  };
}

describe('ADR 038 (amended): the checkout engine owns the backend', () => {
  it('reads where the engine runs from its health, and nothing from an older one', () => {
    expect(engineHomeFromHealth({ status: 'ok', frozen: false, repo_root: ROOT, release_tag: 'v1025', checkout_tag: 'v1027' }))
      .toEqual({ frozen: false, root: ROOT, release_tag: 'v1025', checkout_tag: 'v1027' });
    expect(engineHomeFromHealth({ status: 'ok', frozen: true, repo_root: 'C:\\x\\_MEI', release_tag: 'v1028' }))
      .toEqual({ frozen: true, root: null, release_tag: 'v1028', checkout_tag: null });
    // Before the field existed: ask the checklist instead.
    expect(engineHomeFromHealth({ status: 'ok', release_tag: 'v1025' })).toBeNull();
    expect(engineHomeFromHealth(null)).toBeNull();
  });

  it('owns only from a main checkout with its .env and start script', () => {
    expect(ownerRootFromEngine({ frozen: false, root: ROOT }, disk(ROOT))).toBe(ROOT);
    // An agent's worktree (a .git file, no .env) never becomes the owner (stray-backend lesson).
    expect(ownerRootFromEngine({ frozen: false, root: WORKTREE }, disk(WORKTREE, { gitDir: false }))).toBeNull();
    expect(ownerRootFromEngine({ frozen: false, root: ROOT }, disk(ROOT, { env: false }))).toBeNull();
    expect(ownerRootFromEngine({ frozen: false, root: ROOT }, disk(ROOT, { start: false }))).toBeNull();
    // A packaged engine has no checkout.
    expect(ownerRootFromEngine({ frozen: true, root: null }, disk(ROOT))).toBeNull();
    expect(ownerRootFromEngine(null, disk(ROOT))).toBeNull();
  });

  it('compares Windows folders the way Windows does', () => {
    expect(sameRoot('C:\\Users\\op\\github\\Nova\\', 'c:\\users\\OP\\github\\nova')).toBe(true);
    expect(sameRoot(ROOT, WORKTREE)).toBe(false);
    expect(sameRoot(null, null)).toBe(false);
  });

  it('starts the owner on an empty port, the bundled engine only without one', () => {
    const owner = { repo_root: ROOT, seen_at: 1 };
    expect(emptyPortPlan(owner, disk(ROOT))).toBe('start_owner');
    expect(emptyPortPlan(null, disk(ROOT))).toBe('start_bundled');
    // The checkout was moved or deleted: nothing of it to start.
    expect(emptyPortPlan(owner, disk(ROOT, { start: false }))).toBe('start_bundled');
    expect(ownerUsable(owner, disk(ROOT))).toBe(true);
  });

  it('remembers the owner in one versioned file and ignores anything else', () => {
    const store = new Map<string, string>();
    const fsApi = {
      mkdirSync: () => undefined,
      writeFileSync: (p: string, body: string) => void store.set(p, body),
      renameSync: (from: string, to: string) => {
        store.set(to, store.get(from) ?? '');
        store.delete(from);
      },
    };
    expect(writeEngineOwner(USER_DATA, ROOT, { now: () => 42, fsApi })).toBe(true);
    const file = path.join(USER_DATA, ENGINE_OWNER_FILE);
    const readFile = (p: string) => {
      const body = store.get(p);
      if (body === undefined) throw new Error('ENOENT');
      return body;
    };
    expect(readEngineOwner(USER_DATA, { readFile })).toEqual({ repo_root: ROOT, seen_at: 42 });
    store.set(file, JSON.stringify({ schema_version: 2, repo_root: ROOT }));
    expect(readEngineOwner(USER_DATA, { readFile })).toBeNull();
    store.set(file, '{not json');
    expect(readEngineOwner(USER_DATA, { readFile })).toBeNull();
    store.delete(file);
    expect(readEngineOwner(USER_DATA, { readFile })).toBeNull();
  });

  it('never makes the bundled engine the default, and says what its data means', () => {
    const prompt = ownerStartFailedPrompt({ root: ROOT, error: 'no backend answered within 120 s', userData: USER_DATA });
    expect(prompt.buttons[prompt.defaultId]).toBe('Retry');
    expect(prompt.cancelId).toBe(2);
    expect(prompt.detail).toContain(path.join(USER_DATA, 'cache'));
    expect(prompt.detail).toContain('different Paper account');
  });
});
