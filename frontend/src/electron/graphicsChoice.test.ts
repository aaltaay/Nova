/**
 * Whether the desk draws with the graphics card (operator decision 2026-10-05, #707): the graphics card
 * unless the saved choice or NOVA_ELECTRON_GPU says software, and software when the choice cannot be read.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  GRAPHICS_FILE,
  decideGraphics,
  envGpu,
  parseChoice,
  readChoice,
  writeChoice,
} from '../../electron/graphicsChoice.mjs';

let dir = '';
beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'nova-graphics-'));
});
afterEach(() => {
  fs.rmSync(dir, { recursive: true, force: true });
});

describe('envGpu', () => {
  it('reads yes and no, and nothing else', () => {
    expect(envGpu({ NOVA_ELECTRON_GPU: '1' })).toBe(true);
    expect(envGpu({ NOVA_ELECTRON_GPU: ' Yes ' })).toBe(true);
    expect(envGpu({ NOVA_ELECTRON_GPU: 'false' })).toBe(false);
    expect(envGpu({ NOVA_ELECTRON_GPU: 'maybe' })).toBeNull();
    expect(envGpu({})).toBeNull();
  });
});

describe('the saved choice', () => {
  it('round-trips through the file, through a temp file', () => {
    const choice = { gpu: 'off', reason: 'gpu_crashed', at: 1791200000, detail: 'the graphics process crashed', told: false };
    writeChoice(dir, choice);
    expect(fs.readdirSync(dir)).toEqual([GRAPHICS_FILE]);
    expect(readChoice(dir)).toEqual({ choice: { schema_version: 1, ...choice }, error: null });
  });

  it('is nothing at all when there is no file', () => {
    expect(readChoice(dir)).toEqual({ choice: null, error: null });
  });

  it('refuses another version, a bad mode and broken JSON, saying why', () => {
    expect(parseChoice('{"schema_version": 2, "gpu": "on"}').error).toBe('schema_version 2 is not 1');
    expect(parseChoice('{"schema_version": 1, "gpu": "fast"}').error).toBe('gpu "fast" is not "on" or "off"');
    expect(parseChoice('{oops').error).toMatch(/^not JSON/);
    fs.writeFileSync(path.join(dir, GRAPHICS_FILE), '[]');
    expect(readChoice(dir).error).toMatch(/graphics\.json: schema_version undefined is not 1$/);
  });

  it('reads an unknown reason as the operator\'s', () => {
    expect(parseChoice('{"schema_version": 1, "gpu": "on", "reason": "x"}').choice?.reason).toBe('operator');
  });
});

describe('decideGraphics', () => {
  const none = { choice: null, error: null };
  const off = { choice: { schema_version: 1, gpu: 'off', reason: 'blank_window', at: 1, detail: null, told: false }, error: null };

  it('draws with the graphics card when nothing says otherwise', () => {
    expect(decideGraphics({ env: {}, read: none })).toEqual({ gpu: true, source: 'default', choice: null, error: null });
  });

  it('follows the saved choice', () => {
    expect(decideGraphics({ env: {}, read: off })).toMatchObject({ gpu: false, source: 'choice' });
  });

  it('draws in software when the choice cannot be read', () => {
    expect(decideGraphics({ env: {}, read: { choice: null, error: 'bad' } })).toEqual({
      gpu: false, source: 'unreadable', choice: null, error: 'bad',
    });
  });

  it('lets NOVA_ELECTRON_GPU win over the file, either way', () => {
    expect(decideGraphics({ env: { NOVA_ELECTRON_GPU: '1' }, read: off })).toMatchObject({ gpu: true, source: 'env' });
    expect(decideGraphics({ env: { NOVA_ELECTRON_GPU: '0' }, read: none })).toMatchObject({ gpu: false, source: 'env' });
  });
});
