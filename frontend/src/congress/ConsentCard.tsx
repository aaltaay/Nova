/**
 * The agreement before any read (ADR 066, decision 3): the use rule both sites quote, in the Senate site's words.
 * Nothing is fetched until the operator presses "I understand"; a refused press says why.
 */
import { useState } from 'react';
import { postConsent } from './api';
import { CONSENT_BUTTON, CONSENT_LEAD, CONSENT_TITLE } from './constants';
import type { Consent } from './types';

export function ConsentCard({ consent, onGiven }: { consent: Consent; onGiven: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const agree = async () => {
    setBusy(true);
    setError(null);
    try {
      const next = await postConsent(true);
      if (next.state === 'given') onGiven();
      else setError('The desk did not keep the agreement.');
    } catch (e) {
      setError(`The desk did not keep the agreement: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="cg-card cg-consent" data-testid="congress-consent">
      <h3>{CONSENT_TITLE}</h3>
      <p>{CONSENT_LEAD}</p>
      <blockquote>{consent.text}</blockquote>
      <p className="cg-muted cg-small">{consent.cite}</p>
      <div className="cg-consent__go">
        <button type="button" className="cg-go" onClick={() => void agree()} disabled={busy}
          data-why={busy ? 'Keeping your agreement on the desk' : undefined} data-testid="congress-consent-accept">
          {busy ? 'Keeping it …' : CONSENT_BUTTON}
        </button>
        {error ? <span className="is-down" role="alert">{error}</span> : null}
      </div>
    </section>
  );
}
