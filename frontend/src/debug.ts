/** Enable verbose API logging in the browser console (F12). */
export function isNovaApiDebug(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    if (window.localStorage.getItem('novaApiDebug') === '1') return true;
    return new URLSearchParams(window.location.search).get('apiDebug') === '1';
  } catch {
    return false;
  }
}
