import { useEffect } from 'react';
import { ADVISE_TITLE } from './constants';
import { useAdvise } from './AdviseContext';
import { AdviseControls } from './AdviseControls';
import { AdviseResultCard } from './AdviseResultCard';
import { AdviseTranscript } from './AdviseTranscript';

export function AdviseHost() {
  const { open } = useAdvise();
  if (!open) return null;
  return <AdvisePanel />;
}

export function AdvisePanel() {
  const { closeAdvise, error } = useAdvise();
  // Escape closes Advise like Settings (QA V29): capture phase, so it is the
  // dialog that answers, not a desk hotkey underneath it.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      e.stopPropagation();
      closeAdvise();
    };
    document.addEventListener('keydown', onKey, true);
    return () => document.removeEventListener('keydown', onKey, true);
  }, [closeAdvise]);
  return (
    <div
      className="advise-overlay"
      data-testid="advise-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={ADVISE_TITLE}
    >
      <button
        type="button"
        className="advise-overlay__backdrop"
        aria-label="Close Advise"
        onClick={closeAdvise}
      />
      <div className="advise-overlay__panel">
        <header className="advise-overlay__header">
          <h2>{ADVISE_TITLE}</h2>
          <button type="button" onClick={closeAdvise}>Close</button>
        </header>
        <AdviseControls />
        {error ? (
          <p className="advise-fail" data-testid="advise-error">{error}</p>
        ) : null}
        <div className="advise-overlay__body">
          <AdviseTranscript />
          <AdviseResultCard />
        </div>
      </div>
    </div>
  );
}
