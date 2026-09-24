/**
 * Release notes, newest first: what each release changed, in the words its PR
 * wrote for the operator (tools/release_notes.py). Shared by the update notice
 * (what an update would bring) and the What's new card (what it brought).
 * Plain text only -- nothing from GitHub is rendered as HTML.
 */
import { kindLabel, type ReleaseNotes, type UpdateAction } from './updateView';

interface Props {
  notes: ReleaseNotes | null;
  act: (action: UpdateAction, url?: string) => void;
}

export function ReleaseNotesList({ notes, act }: Props) {
  if (!notes || notes.loading) {
    return <p className="nova-release-notes__status">Loading release notes…</p>;
  }
  const { releases, more, olderUnlisted, error, pageUrl } = notes;
  return (
    <div className="nova-release-notes">
      {error && <p className="nova-release-notes__status nova-release-notes__status--error">{error}</p>}
      {!error && releases.length === 0 && (
        <p className="nova-release-notes__status">No release notes were found for these versions.</p>
      )}
      {releases.length > 0 && (
        <ol className="nova-release-notes__list">
          {releases.map((note) => (
            <li key={note.tag} className="nova-release-notes__item" data-testid="release-note">
              <div className="nova-release-notes__head">
                <span className="nova-release-notes__tag">{note.tag}</span>
                {note.kind && (
                  <span className="nova-release-notes__kind" data-kind={note.kind}>
                    {kindLabel(note.kind)}
                  </span>
                )}
                <span className="nova-release-notes__title">
                  {note.recorded ? note.title : 'No release notes were recorded for this release.'}
                </span>
              </div>
              {note.summary && <p className="nova-release-notes__summary">{note.summary}</p>}
              {note.points.length > 0 && (
                <ul className="nova-release-notes__points">
                  {note.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              )}
              {note.prUrl && (
                <button type="button" className="nova-release-notes__link" onClick={() => act('open-link', note.prUrl ?? undefined)}>
                  Pull request #{note.pr}
                </button>
              )}
            </li>
          ))}
        </ol>
      )}
      {(more > 0 || olderUnlisted) && (
        <p className="nova-release-notes__status">
          {more > 0 ? `…and ${more} more ${more === 1 ? 'release' : 'releases'}` : 'Older releases'} are on GitHub.
        </p>
      )}
      {pageUrl && (
        <button type="button" className="nova-release-notes__link" onClick={() => act('open-link', pageUrl)}>
          All releases on GitHub
        </button>
      )}
    </div>
  );
}
