/**
 * View > "Draw with the graphics card" (operator decision 2026-10-05, #707): the switch shows how the desk
 * draws, restarts Nova to change it only once the operator says so, and says why when the safety net
 * turned the graphics card off -- once.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readChoice } from '../../electron/graphicsChoice.mjs';
import { GRAPHICS_MENU_LABEL, createGraphicsMenu, fallbackNotice, graphicsMenuItems, graphicsNote } from '../../electron/graphicsMenu.mjs';

type Item = { label: string; type?: string; checked?: boolean; enabled?: boolean; click?: () => void };

const at = new Date(2026, 9, 5, 10, 31).getTime() / 1000;
const crashed = { schema_version: 1, gpu: 'off', reason: 'gpu_crashed', at, detail: 'the graphics process crashed (exit code 1)', told: false };
const blank = { ...crashed, reason: 'blank_window', detail: null };

describe('the switch', () => {
  it('is checked while the desk draws with the graphics card, with no note', () => {
    const items = graphicsMenuItems({ gpu: true, source: 'default', choice: null }, { onToggle: () => {} }) as Item[];
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({ label: GRAPHICS_MENU_LABEL, type: 'checkbox', checked: true, enabled: true });
  });

  it('says why the safety net turned it off, and when', () => {
    expect(graphicsNote({ gpu: false, source: 'choice', choice: blank })).toBe('Off: the window went blank at 10:31');
    expect(graphicsNote({ gpu: false, source: 'choice', choice: crashed }, {}, true)).toBe(
      'Off from the next start: the graphics process stopped at 10:31',
    );
    expect(graphicsNote({ gpu: false, source: 'choice', choice: { ...blank, reason: 'operator' } })).toBeNull();
  });

  it('is locked while NOVA_ELECTRON_GPU decides, and says so', () => {
    const items = graphicsMenuItems({ gpu: true, source: 'env', choice: null }, { env: { NOVA_ELECTRON_GPU: '1' }, onToggle: () => {} }) as Item[];
    expect(items[0].enabled).toBe(false);
    expect(items[1]).toEqual({ label: 'Set by NOVA_ELECTRON_GPU=1; remove it to choose here', enabled: false });
  });
});

describe('fallbackNotice', () => {
  it('words a crash during the run, a start after one, and a blank window', () => {
    expect(fallbackNotice(crashed, { during: true })?.message).toBe("The graphics card's process stopped.");
    expect(fallbackNotice(crashed, { during: true })?.detail).toMatch(/^It stopped at 10:31 \(the graphics process crashed \(exit code 1\)\)\. Nova keeps running\./);
    expect(fallbackNotice(crashed)?.message).toBe('Nova draws in software.');
    expect(fallbackNotice(blank)?.message).toBe('Nova restarted to draw in software.');
    expect(fallbackNotice(blank)?.detail).toMatch(/View > Draw with the graphics card turns it back on\.$/);
    expect(fallbackNotice({ ...blank, reason: 'operator' })).toBeNull();
  });
});

describe('createGraphicsMenu', () => {
  let dir = '';
  let rendered: Item[][] = [];
  const responses: number[] = [];
  const dialog = { showMessageBox: vi.fn(async () => ({ response: responses.shift() ?? 0 })) };
  const app = { relaunch: vi.fn(), quit: vi.fn() };
  const make = (decision: object) => createGraphicsMenu({
    decision,
    env: {},
    userData: dir,
    dialog,
    app,
    setViewExtras: (items: Item[]) => {
      rendered.push(items);
      return null;
    },
    now: () => at * 1000,
  });

  beforeEach(() => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), 'nova-gmenu-'));
    rendered = [];
    responses.length = 0;
    dialog.showMessageBox.mockClear();
    app.relaunch.mockClear();
    app.quit.mockClear();
  });
  afterEach(() => {
    fs.rmSync(dir, { recursive: true, force: true });
  });

  it('restarts in software only after the operator says so', async () => {
    const menu = make({ gpu: true, source: 'default', choice: null });
    menu.render();
    responses.push(1); // Cancel
    rendered[0][0].click?.();
    await vi.waitFor(() => expect(rendered).toHaveLength(2)); // the checkbox is put back
    expect(app.relaunch).not.toHaveBeenCalled();
    expect(readChoice(dir).choice).toBeNull();
    responses.push(0); // Restart now
    rendered[1][0].click?.();
    await vi.waitFor(() => expect(app.quit).toHaveBeenCalledOnce());
    expect(app.relaunch).toHaveBeenCalledOnce();
    expect(readChoice(dir).choice).toMatchObject({ gpu: 'off', reason: 'operator', told: true });
  });

  it('tells the operator once why this start draws in software', async () => {
    const menu = make({ gpu: false, source: 'choice', choice: blank });
    await expect(menu.tellIfOwed()).resolves.toBe(true);
    expect(dialog.showMessageBox).toHaveBeenCalledOnce();
    expect(readChoice(dir).choice?.told).toBe(true);
    const again = make({ gpu: false, source: 'choice', choice: readChoice(dir).choice });
    await expect(again.tellIfOwed()).resolves.toBe(false);
    expect(dialog.showMessageBox).toHaveBeenCalledOnce();
  });

  it('marks a fallback during the run as off from the next start', () => {
    const menu = make({ gpu: true, source: 'default', choice: null });
    menu.fellBack(crashed);
    const last = rendered[rendered.length - 1];
    expect(last[0].checked).toBe(false);
    expect(last[1].label).toBe('Off from the next start: the graphics process stopped at 10:31');
  });
});
