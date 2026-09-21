import { describe, expect, it } from 'vitest';
import {
  DESK_VENUE_LEGACY_PAPER_GATEWAY_LABEL,
  DESK_VENUE_LEGACY_PAPER_GATEWAY_TITLE,
  DESK_VENUE_LIVE_TITLE,
  DESK_VENUE_PAPER_BANNER_TEXT,
  DESK_VENUE_PAPER_TITLE,
  DESK_VENUE_SIM_TITLE,
  deskVenuePracticeAccountTooltip,
  isPracticeAccountId,
} from './desk_venue';

describe('desk_venue copy (ADR 020)', () => {
  it('says what each venue is', () => {
    expect(DESK_VENUE_LIVE_TITLE).toMatch(/IBKR, real money/);
    expect(DESK_VENUE_PAPER_TITLE).toMatch(/Nova's practice account/);
    expect(DESK_VENUE_PAPER_TITLE).toMatch(/fake money/i);
    expect(DESK_VENUE_PAPER_TITLE).toMatch(/live data/i);
    expect(DESK_VENUE_SIM_TITLE).toMatch(/replay playground/);
  });

  it('never describes Paper as an IBKR paper account', () => {
    expect(DESK_VENUE_PAPER_BANNER_TEXT).toMatch(/Nova's practice account/);
    expect(DESK_VENUE_PAPER_BANNER_TEXT).not.toMatch(/IBKR paper account/);
    expect(DESK_VENUE_PAPER_TITLE).not.toMatch(/port 4002/);
  });

  it('marks the IBKR paper Gateway launcher as legacy and not the venue', () => {
    expect(DESK_VENUE_LEGACY_PAPER_GATEWAY_LABEL).toMatch(/legacy/i);
    expect(DESK_VENUE_LEGACY_PAPER_GATEWAY_TITLE).toMatch(/not the Paper venue/);
  });

  it('recognises the practice account ids and describes them as Nova-managed', () => {
    expect(isPracticeAccountId('NOVA-PAPER')).toBe(true);
    expect(isPracticeAccountId('NOVA-SIM')).toBe(true);
    expect(isPracticeAccountId('DUQ266899')).toBe(false);
    expect(isPracticeAccountId(null)).toBe(false);
    expect(deskVenuePracticeAccountTooltip('NOVA-PAPER')).toMatch(/Nova-managed/);
    expect(deskVenuePracticeAccountTooltip('NOVA-PAPER')).toMatch(/fake money/i);
    expect(deskVenuePracticeAccountTooltip('NOVA-SIM')).toMatch(/replay/);
  });
});
