/**
 * Entry of the phone page (`phone.html`, ADR 070). It does one thing before anything else loads:
 * say where the API is. A page this PC serves talks to the local API; a page reached through the
 * tunnel talks to the same name on the tunnel's API port. The desk's modules read that address
 * once, when they load, so they are imported only after it is set.
 */
import { apiBaseFor } from '../phone_link/linkStats';

window.__NOVA_API_BASE__ = apiBaseFor(window.location);

void import('./mountPhone').then(
  ({ mountPhone }) => mountPhone(),
  (err: unknown) => {
    console.error(err);
    const el = document.getElementById('root');
    if (el) el.textContent = 'Nova could not start on this phone. Reload the page.';
  },
);
