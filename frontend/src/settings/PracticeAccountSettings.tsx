/**
 * Settings > Trade > Practice Account -- reset Nova's Paper and Sim ledgers (ADR 020).
 */
import {
  PRACTICE_SETTINGS_HINT,
  PRACTICE_SETTINGS_TITLE,
  PRACTICE_VENUES,
} from '../constantGroups/practice';
import { PracticeResetAction } from '../practice/PracticeResetAction';

export function PracticeAccountSettings() {
  return (
    <section className="settings-block practice-settings" data-testid="practice-account-settings">
      <h3 className="settings-block-title">{PRACTICE_SETTINGS_TITLE}</h3>
      <p className="settings-block-hint">{PRACTICE_SETTINGS_HINT}</p>
      {PRACTICE_VENUES.map((venue) => (
        <PracticeResetAction key={venue} venue={venue} />
      ))}
    </section>
  );
}
