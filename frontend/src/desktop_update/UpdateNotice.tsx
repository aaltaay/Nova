/**
 * The update notice: a strip under the header that says a newer Nova is out and
 * asks -- Update or Later -- then follows the download to Restart to update.
 * Nothing downloads before Update and nothing restarts before Restart to update
 * (electron/updatePolicy.mjs). It never takes keyboard focus, so a hot key
 * pressed while it appears still reaches the desk.
 */
import { useState } from 'react';
import { ReleaseNotesList } from './ReleaseNotesList';
import type { UpdateAction, UpdateNotice as Notice } from './updateView';

interface Props {
  notice: Notice;
  act: (action: UpdateAction, url?: string) => void;
}

function message(notice: Notice): string {
  const { stage, tag, installed, percent, retry, error } = notice;
  switch (stage) {
    case 'available':
      return `Nova ${tag} is available${installed ? ` — you have ${installed}` : ''}.`;
    case 'downloading':
      return retry
        ? `Downloading Nova ${tag}… ${percent}% — connection dropped, retrying (attempt ${retry}).`
        : `Downloading Nova ${tag}… ${percent}%`;
    case 'stopped':
      return `The download of Nova ${tag} stopped at ${percent}%${error ? `: ${error}` : ''}. What arrived is kept.`;
    case 'ready':
      return `Nova ${tag} is ready to install.${error ? ` Last attempt failed: ${error}` : ''}`;
    case 'installing':
      return `Installing Nova ${tag}…`;
  }
}

const HINTS: Partial<Record<Notice['stage'], string>> = {
  available: 'Update downloads it now; Nova restarts only when you choose Restart to update.',
  ready: 'Restart closes Nova and its engine, installs the update and reopens Nova, usually within a minute; an "Updating Nova" window shows each step.',
};

export function UpdateNotice({ notice, act }: Props) {
  const [showNotes, setShowNotes] = useState(false);
  const { stage, notes } = notice;
  const listed = notes && !notes.loading ? notes.releases.length : 0;
  const hint = HINTS[stage];
  return (
    <div className="nova-update-notice" role="status" data-stage={stage} data-testid="update-notice">
      <div className="nova-update-notice__row">
        <span className="nova-update-notice__mark" aria-hidden="true">
          ↑
        </span>
        <span className="nova-update-notice__text">
          {message(notice)}
          {hint && <span className="nova-update-notice__hint"> {hint}</span>}
        </span>
        <span className="nova-update-notice__actions">
          {stage !== 'installing' && (
            <button
              type="button"
              className="nova-update-notice__btn nova-update-notice__btn--quiet"
              aria-expanded={showNotes}
              onClick={() => setShowNotes((open) => !open)}
            >
              {showNotes ? 'Hide notes' : `What's new${listed ? ` (${listed})` : ''}`}
            </button>
          )}
          {stage === 'available' && (
            <button type="button" className="nova-update-notice__btn nova-update-notice__btn--primary" onClick={() => act('download')}>
              Update
            </button>
          )}
          {stage === 'stopped' && (
            <button type="button" className="nova-update-notice__btn nova-update-notice__btn--primary" onClick={() => act('download')}>
              Resume
            </button>
          )}
          {stage === 'ready' && (
            <button type="button" className="nova-update-notice__btn nova-update-notice__btn--primary" onClick={() => act('restart')}>
              Restart to update
            </button>
          )}
          {stage !== 'installing' && (
            <button type="button" className="nova-update-notice__btn" onClick={() => act('later')}>
              {stage === 'downloading' ? 'Hide' : 'Later'}
            </button>
          )}
        </span>
      </div>
      {stage === 'downloading' && (
        <div className="nova-update-notice__progress" aria-hidden="true">
          <div className="nova-update-notice__progress-bar" style={{ width: `${notice.percent}%` }} />
        </div>
      )}
      {showNotes && stage !== 'installing' && (
        <div className="nova-update-notice__notes">
          <ReleaseNotesList notes={notes} act={act} />
        </div>
      )}
    </div>
  );
}
