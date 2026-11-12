/**
 * Starts the phone page. Loaded by `phoneMain.tsx` only after the API's address is set, because the
 * desk modules under it read that address once, when they load.
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/inter/wght.css';
import '@fontsource-variable/jetbrains-mono/wght.css';
import { applyTheme } from '../theme/themePrefs';
import { installWhyTip } from '../ux/whyTip';
import './phoneDesk.css';
import './phone.css';
import PhoneApp from './PhoneApp';

interface WakeLockNavigator {
  wakeLock?: { request(type: 'screen'): Promise<unknown> };
}

/** Keep the screen on while the page is in front: a phone that sleeps mid-trade shows nothing. */
function keepAwake(): void {
  const ask = (): void => {
    if (document.hidden) return;
    const lock = (navigator as Navigator & WakeLockNavigator).wakeLock;
    lock?.request('screen').catch((err: unknown) => console.debug('[Nova phone] the screen may sleep', err));
  };
  document.addEventListener('visibilitychange', ask);
  ask();
}

export function mountPhone(): void {
  const rootEl = document.getElementById('root');
  if (!rootEl) throw new Error('#root missing');
  // The phone is always dark: the desk's chart tokens read this.
  applyTheme('dark');
  // A locked control says why when it is pressed (the desk's own rule).
  installWhyTip(document);
  keepAwake();
  createRoot(rootEl).render(
    <StrictMode>
      <PhoneApp />
    </StrictMode>,
  );
}
