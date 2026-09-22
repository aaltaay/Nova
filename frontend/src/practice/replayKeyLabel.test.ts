import { describe, expect, it } from 'vitest';
import { formatReplayKey } from './replayKeyLabel';

describe('formatReplayKey', () => {
  it('renders the backend list shape -- a historical window and a recording', () => {
    expect(formatReplayKey(['historical', 'GDC', '2026-09-21', '09:15', '11:30'])).toBe(
      'GDC · 2026-09-21 · 09:15–11:30 (download)',
    );
    expect(formatReplayKey(['capture', 'GRML', '2026-09-21'])).toBe('GRML · 2026-09-21 (recording)');
  });

  it('still accepts a plain string, trimmed, and treats nothing loaded as empty', () => {
    expect(formatReplayKey('  GRML|2026-09-21 ')).toBe('GRML|2026-09-21');
    expect(formatReplayKey(null)).toBe('');
    expect(formatReplayKey(undefined)).toBe('');
    expect(formatReplayKey([])).toBe('');
  });

  it('never throws on an unknown source or odd members', () => {
    expect(formatReplayKey(['weird', 'ABCD', null, 5])).toBe('ABCD · 5 (weird)');
  });

  it('maps members by position: a null one never shifts the rest (C66)', () => {
    // The date is missing: the window must not read as the date.
    expect(formatReplayKey(['historical', 'GDC', null, '09:15', '11:30'])).toBe('GDC · 09:15–11:30 (download)');
    expect(formatReplayKey([null, 'GRML', '2026-09-21'])).toBe('GRML · 2026-09-21');
    expect(formatReplayKey(['capture', null, '2026-09-21'])).toBe('2026-09-21 (recording)');
    expect(formatReplayKey([null, null, null])).toBe('');
  });
});
