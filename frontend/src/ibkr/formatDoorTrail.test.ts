import { describe, expect, it } from 'vitest';
import {
  doorTrailEventLabel,
  formatDoorTrailLine,
  newestFirst,
} from './formatDoorTrail';

describe('formatDoorTrail', () => {
  it('labels known IBC 2FA and click events', () => {
    expect(doorTrailEventLabel('ibc_second_factor')).toBe(
      'Second Factor / IBKR Mobile',
    );
    expect(doorTrailEventLabel('click')).toBe('Click');
  });

  it('builds a readable line without inventing account ids', () => {
    const line = formatDoorTrailLine({
      actor: 'operator',
      event: 'click',
      requested: 'live',
      plan: 'start_ibc',
      launch_action: 'launched_ibc',
      note: 'Watch the desktop for SECOND FACTOR',
    });
    expect(line).toContain('Click');
    expect(line).toContain('live');
    expect(line).toContain('start_ibc');
    expect(line).not.toMatch(/\bU\d{5,}\b/);
  });

  it('shows newest first for the operator list', () => {
    const rows = newestFirst([
      { event: 'click', ts: 1 },
      { event: 'attached', ts: 2 },
    ]);
    expect(rows[0]?.event).toBe('attached');
  });
});
