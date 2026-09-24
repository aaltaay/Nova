/**
 * What's new: after an update, the first launch of the new version opens this
 * card with the notes of every release the update brought; Help > What's New
 * opens it again. A floating card, not a modal -- the desk stays usable and
 * keyboard focus stays where it was, so hot keys keep working while it is open.
 * Closing it records the version as read (electron/whatsNew.mjs). File an issue opens the desk's
 * issue form (issue_report/).
 */
import { openIssueForm } from '../issue_report';
import { ReleaseNotesList } from './ReleaseNotesList';
import type { UpdateAction, WhatsNew } from './updateView';

interface Props {
  whatsNew: WhatsNew;
  act: (action: UpdateAction, url?: string) => void;
}

function subtitle({ mode, since, notes }: WhatsNew): string {
  if (mode === 'recent') return 'The latest releases up to this version.';
  const count = notes.loading ? 0 : notes.releases.length;
  if (!since) return 'Nova was updated.';
  return count > 1 ? `Updated from ${since} — ${count} releases.` : `Updated from ${since}.`;
}

export function WhatsNewCard({ whatsNew, act }: Props) {
  const close = () => act('whats-new-close');
  return (
    <section className="nova-whats-new" aria-labelledby="nova-whats-new-title" data-testid="whats-new">
      <header className="nova-whats-new__head">
        <div>
          <h2 id="nova-whats-new-title" className="nova-whats-new__title">
            What&apos;s new in Nova {whatsNew.tag}
          </h2>
          <p className="nova-whats-new__subtitle">{subtitle(whatsNew)}</p>
        </div>
        <button type="button" className="nova-whats-new__close" aria-label="Close What's new" onClick={close}>
          ×
        </button>
      </header>
      <div className="nova-whats-new__body">
        <ReleaseNotesList notes={whatsNew.notes} act={act} />
      </div>
      <footer className="nova-whats-new__foot">
        {/* Something off after the update, or something to ask for: one click to GitHub. */}
        <button type="button" className="nova-update-notice__btn" onClick={openIssueForm}>
          ⚑ File an issue
        </button>
        <button type="button" className="nova-update-notice__btn nova-update-notice__btn--primary" onClick={close}>
          Got it
        </button>
      </footer>
    </section>
  );
}
