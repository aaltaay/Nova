/**
 * The desk's application menu: Electron's Windows menus, with View adding how the desk draws
 * (graphicsMenu.mjs) and Help the in-app updater's rows (updateAsk.mjs). One owner, so neither drops
 * the other's rows; the native menu stays usable while the page is blank, which is why the graphics
 * switch lives there.
 */
import { Menu } from 'electron';

let help = null;
let viewExtras = [];

/** Electron's Windows View menu, then `extras`. */
function viewMenu(extras) {
  return {
    label: 'View',
    submenu: [
      { role: 'reload' },
      { role: 'forceReload' },
      { role: 'toggleDevTools' },
      { type: 'separator' },
      { role: 'resetZoom' },
      { role: 'zoomIn' },
      { role: 'zoomOut' },
      { type: 'separator' },
      { role: 'togglefullscreen' },
      ...(extras.length ? [{ type: 'separator' }, ...extras] : []),
    ],
  };
}

/** The template: File, Edit, View (with `viewItems`), Window, and Help once it has rows. */
export function appMenuTemplate({ helpItems = null, viewItems = [] } = {}) {
  return [
    { role: 'fileMenu' },
    { role: 'editMenu' },
    viewMenu(viewItems),
    { role: 'windowMenu' },
    ...(helpItems ? [{ role: 'help', submenu: helpItems }] : []),
  ];
}

/** Set the menu from the current rows; returns why it could not be, or null. */
function render() {
  try {
    Menu.setApplicationMenu(Menu.buildFromTemplate(appMenuTemplate({ helpItems: help, viewItems: viewExtras })));
    return null;
  } catch (err) {
    return err instanceof Error ? err.message : String(err);
  }
}

/** Help's rows (the updater's). */
export function setHelpMenu(items) {
  help = items;
  return render();
}

/** View's own rows, after Electron's. */
export function setViewExtras(items) {
  viewExtras = items;
  return render();
}
