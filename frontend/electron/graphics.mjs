/**
 * How the desk draws, started (operator decision 2026-10-05, #707): the View menu's graphics switch
 * (graphicsMenu.mjs), and while the graphics card draws, its safety net (graphicsWatch.mjs) -- a crash of
 * the graphics process is told at once and drawn in software from the next start; a blank window
 * restarts Nova in software. The decision itself is made before the app is ready (gpuPolicy.mjs).
 */
import { setViewExtras } from './appMenu.mjs';
import { createGraphicsMenu } from './graphicsMenu.mjs';
import { startGraphicsWatch } from './graphicsWatch.mjs';

/** Returns the menu (its `tellIfOwed` runs once the desk shows). */
export function startGraphics({ decision, app, BrowserWindow, screen, powerMonitor, dialog, sampler, isDeskWindow }) {
  const userData = app.getPath('userData');
  const menu = createGraphicsMenu({ decision, userData, dialog, app, setViewExtras });
  menu.render();
  if (!decision.gpu) return menu;
  const watch = startGraphicsWatch({
    app,
    BrowserWindow,
    screen,
    powerMonitor,
    sampler,
    isDeskWindow,
    userData,
    onFallback: ({ reason, choice }) => {
      menu.fellBack(choice);
      if (reason === 'blank_window') {
        app.relaunch();
        app.quit();
      } else {
        void menu.tell(choice, { during: true });
      }
    },
  });
  app.on('will-quit', () => watch.stop());
  return menu;
}
