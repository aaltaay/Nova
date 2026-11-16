/**
 * The phone page notice (ADR 070 amendment 2026-11-14): a strip beside the backend notice, only while the phone
 * is behind the desk -- the page did not rebuild, or its server did not come up after the desk started it. The
 * desk keeps trying by itself (electron/phonePageKeeper.mjs), so there is nothing to press; the strip goes away
 * once it is fixed. Later hides it until what it says changes. Never takes keyboard focus, like the update notice.
 */
import { useState } from 'react';
import type { PhonePage } from './updateView';

export type PhonePageNoticeModel = { key: string; text: string; hint: string };

/** What the strip says, or null when the phone has the desk's page and it is served. */
export function phonePageNotice(page: PhonePage): PhonePageNoticeModel | null {
  const why = page.last?.outcome === 'failed' ? page.last.text : '';
  if (page.build === 'failed') {
    return {
      key: `build:${why}`,
      text: 'The phone page did not rebuild for this release: the phone still shows the one before.',
      hint: why ? `${why}. Nova tries again in 30 minutes, or when the code changes.` : 'Nova tries again in 30 minutes, or when the code changes.',
    };
  }
  if (page.served === false && page.last?.outcome !== 'started') {
    return {
      key: `served:${why}`,
      text: 'The phone page server is not running: the phone cannot load Nova.',
      hint: why ? `${why}. Nova tries again every minute.` : 'Nova tries again every minute.',
    };
  }
  return null;
}

export function PhonePageNotice({ phonePage }: { phonePage: PhonePage }) {
  const [later, setLater] = useState<string | null>(null);
  const model = phonePageNotice(phonePage);
  if (!model || model.key === later) return null;
  return (
    <div className="nova-update-notice" role="status" data-stage="phone-page" data-testid="phone-page-notice">
      <div className="nova-update-notice__row">
        <span className="nova-update-notice__mark" aria-hidden="true">
          ⟳
        </span>
        <span className="nova-update-notice__text">
          {model.text}
          <span className="nova-update-notice__hint"> {model.hint}</span>
        </span>
        <span className="nova-update-notice__actions">
          <button type="button" className="nova-update-notice__btn" onClick={() => setLater(model.key)}>
            Later
          </button>
        </span>
      </div>
    </div>
  );
}
