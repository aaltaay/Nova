/**
 * One owner for the application menu: the graphics switch in View and the updater's rows in Help never
 * drop each other.
 */
import { describe, expect, it, vi } from 'vitest';

const h = vi.hoisted(() => ({ menu: [] as { label?: string; role?: string; submenu?: { label?: string; role?: string }[] }[] }));

vi.mock('electron', () => ({
  Menu: {
    buildFromTemplate: (t: unknown) => t,
    setApplicationMenu: (m: typeof h.menu) => {
      h.menu = m;
    },
  },
}));

const { appMenuTemplate, setHelpMenu, setViewExtras } = await import('../../electron/appMenu.mjs');

describe('the application menu', () => {
  it("keeps Electron's Windows View rows and adds the desk's after them", () => {
    const view = appMenuTemplate({ viewItems: [{ label: 'Draw with the graphics card' }] })[2];
    expect(view.label).toBe('View');
    expect(view.submenu.slice(0, 3).map((r: { role?: string }) => r.role)).toEqual(['reload', 'forceReload', 'toggleDevTools']);
    expect(view.submenu.at(-1)).toEqual({ label: 'Draw with the graphics card' });
  });

  it('has no Help until the updater gives it rows', () => {
    expect(appMenuTemplate().map((r) => r.role ?? r.label)).toEqual(['fileMenu', 'editMenu', 'View', 'windowMenu']);
  });

  it('keeps View when Help changes, and Help when View changes', () => {
    expect(setViewExtras([{ label: 'Draw with the graphics card' }])).toBeNull();
    expect(setHelpMenu([{ label: 'Check for Updates' }])).toBeNull();
    expect(h.menu.find((r) => r.role === 'help')?.submenu).toEqual([{ label: 'Check for Updates' }]);
    expect(h.menu.find((r) => r.label === 'View')?.submenu?.at(-1)).toEqual({ label: 'Draw with the graphics card' });
    setViewExtras([{ label: 'Off: the window went blank' }]);
    expect(h.menu.find((r) => r.role === 'help')?.submenu).toEqual([{ label: 'Check for Updates' }]);
  });
});
