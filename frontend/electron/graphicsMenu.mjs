/**
 * View > "Draw with the graphics card" (operator decision 2026-10-05, #707): how the desk draws, a switch
 * that restarts Nova to change it, and the words for the operator when the safety net (graphicsWatch.mjs)
 * turned the graphics card off. The menu is native, so it still works over a blank page. Electron's dialog
 * and app are passed in (main.mjs), so this is testable without it.
 */
import { GPU_ENV, writeChoice } from './graphicsChoice.mjs';

export const GRAPHICS_MENU_LABEL = 'Draw with the graphics card';
const SLOWER = 'Dragging the charts is slower in software.';
const TURN_BACK = 'View > Draw with the graphics card turns it back on.';

/** Local HH:MM of epoch seconds, or null. */
export function clockOf(epochSec) {
  if (typeof epochSec !== 'number' || !Number.isFinite(epochSec)) return null;
  const d = new Date(epochSec * 1000);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

const since = (choice) => {
  const at = clockOf(choice?.at);
  return at ? ` at ${at}` : '';
};

/**
 * The menu's note under the switch, or null. `pending`: the safety net turned the graphics card off during
 * this run, which still draws with it until Nova starts again.
 */
export function graphicsNote(decision, env = {}, pending = false) {
  if (decision.source === 'env') return `Set by ${GPU_ENV}=${env[GPU_ENV] ?? ''}; remove it to choose here`;
  if (decision.source === 'unreadable') return 'In software: the saved choice could not be read';
  const c = decision.choice;
  if (!c || c.gpu !== 'off' || c.reason === 'operator') return null;
  const why = c.reason === 'gpu_crashed' ? 'the graphics process stopped' : 'the window went blank';
  return pending ? `Off from the next start: ${why}${since(c)}` : `Off: ${why}${since(c)}`;
}

/** View's rows: the switch (checked while the desk draws, or will draw, with the graphics card) and its note. */
export function graphicsMenuItems(decision, { env = {}, pending = false, onToggle }) {
  const note = graphicsNote(decision, env, pending);
  return [
    {
      label: GRAPHICS_MENU_LABEL,
      type: 'checkbox',
      checked: decision.gpu,
      enabled: decision.source !== 'env',
      click: onToggle,
    },
    ...(note ? [{ label: note, enabled: false }] : []),
  ];
}

/**
 * What to tell the operator about a choice the safety net made, or null. `during`: Nova still runs on the
 * graphics card after its process stopped; otherwise this start already draws in software.
 */
export function fallbackNotice(choice, { during = false } = {}) {
  if (!choice || choice.gpu !== 'off' || choice.reason === 'operator') return null;
  const detail = choice.detail ? ` (${choice.detail})` : '';
  if (choice.reason === 'gpu_crashed' && during) {
    return {
      message: "The graphics card's process stopped.",
      detail: `It stopped${since(choice)}${detail}. Nova keeps running. From its next start it draws in software. ${SLOWER} ${TURN_BACK}`,
    };
  }
  if (choice.reason === 'gpu_crashed') {
    return {
      message: 'Nova draws in software.',
      detail: `The graphics card's process stopped${since(choice)}${detail}, so Nova started without it. ${SLOWER} ${TURN_BACK}`,
    };
  }
  return {
    message: 'Nova restarted to draw in software.',
    detail: `The window went blank${since(choice)} while the graphics card drew it${detail}, so Nova restarted without it. ${SLOWER} ${TURN_BACK}`,
  };
}

/**
 * The switch in View and the notices. `setViewExtras` is appMenu.mjs's; `dialog` / `app` Electron's.
 */
export function createGraphicsMenu({ decision, env = process.env, userData, dialog, app, setViewExtras, logger = console, now = () => Date.now() }) {
  let current = decision;
  let pending = false;

  function render() {
    const failed = setViewExtras(graphicsMenuItems(current, { env, pending, onToggle: () => void toggle() }));
    if (failed) logger.error(`[nova] graphics: menu not set (${failed})`);
  }

  async function toggle() {
    const next = !current.gpu;
    const { response } = await dialog.showMessageBox({
      type: 'question',
      title: 'Nova',
      buttons: ['Restart now', 'Cancel'],
      defaultId: 0,
      cancelId: 1,
      message: next ? 'Draw with the graphics card?' : 'Draw in software?',
      detail: next
        ? 'Nova closes and opens again to draw with the graphics card, which makes dragging the charts faster. If the window goes blank, Nova switches back by itself.'
        : `Nova closes and opens again to draw in software. ${SLOWER}`,
    });
    if (response !== 0) {
      render(); // the checkbox flipped on the click: put it back
      return;
    }
    try {
      writeChoice(userData, { gpu: next ? 'on' : 'off', reason: 'operator', at: Math.round(now() / 1000), detail: null, told: true });
    } catch (err) {
      const why = err instanceof Error ? err.message : String(err);
      logger.error(`[nova] graphics: could not save the choice (${why})`);
      await dialog.showMessageBox({ type: 'error', title: 'Nova', buttons: ['OK'], message: 'The choice could not be saved.', detail: why });
      render();
      return;
    }
    app.relaunch();
    app.quit();
  }

  /** Tell the operator once (no parent window: it never blocks the trading window), then remember it was told. */
  async function tell(choice, { during = false } = {}) {
    const notice = fallbackNotice(choice, { during });
    if (!notice || choice.told) return false;
    await dialog.showMessageBox({ type: 'warning', title: 'Nova', buttons: ['OK'], ...notice });
    try {
      writeChoice(userData, { ...choice, told: true });
    } catch (err) {
      logger.error(`[nova] graphics: could not remember the notice (${err instanceof Error ? err.message : String(err)})`);
    }
    return true;
  }

  return {
    render,
    /** The safety net stored "software" during this run (graphicsWatch.mjs). */
    fellBack(choice) {
      current = { gpu: false, source: 'choice', choice, error: null };
      pending = true;
      render();
    },
    /** This start draws in software because of the safety net and the operator has not been told. */
    tellIfOwed() {
      return current.source === 'choice' ? tell(current.choice) : Promise.resolve(false);
    },
    tell,
  };
}
