/**
 * What a proposal means for the operator's own Stage (ADR 042 draft): Nova takes it, it is not a trade, the
 * size the risk per trade buys -- read off raw board frames, never trusted.
 */
import { describe, expect, it } from 'vitest';
import { SAMPLE_SETUPS_BOARD } from '../sample_data/sampleSetups';
import {
  notATradeText,
  proposalNotATrade,
  proposalStageLock,
  proposalStageSize,
  proposalTakenBy,
  proposalVerdictLine,
  stageLimit,
} from './proposalVerdict';
import { stagedLimit } from './setupsFormat';
import type { SetupProposal } from './types';

const NVXA = SAMPLE_SETUPS_BOARD.rows[0].proposal as SetupProposal;      // entry 4.38, stop 4.30, risk 0.08

describe('a proposal and the operator', () => {
  it('reads who takes it and why it is not a trade, dropping what is mistyped', () => {
    expect(proposalTakenBy({ ...NVXA, taken_by: 'bot' })).toBe('bot');
    expect(proposalTakenBy({ ...NVXA, taken_by: 'auto_entry' })).toBe('auto_entry');
    expect(proposalTakenBy({ ...NVXA, taken_by: 'someone' as never })).toBeNull();
    expect(proposalTakenBy(NVXA)).toBeNull();                                        // an older API
    expect(proposalNotATrade({ ...NVXA, not_a_trade: { reasons: ['grade C', 7 as never, ' '] } })).toEqual(['grade C']);
    expect(proposalNotATrade({ ...NVXA, not_a_trade: { reasons: [] } })).toEqual([]);
    expect(proposalNotATrade({ ...NVXA, not_a_trade: null })).toBeNull();
    expect(notATradeText([])).toBe('Not a trade.');
    expect(proposalVerdictLine(NVXA)).toBeNull();
  });

  it('sizes Stage by the risk per trade over the risk a share, and says where it came from', () => {
    expect(proposalStageSize(NVXA, 20, "the Paper sleeve's risk per trade")).toEqual({
      qty: 250, text: "250 shares: $20 of risk (the Paper sleeve's risk per trade) over 8¢ a share",
    });
    // No risk on the proposal: entry minus stop.
    expect(proposalStageSize({ risk: null, entry: 4.38, stop: 4.30 }, 20, 'x').qty).toBe(250);
    expect(proposalStageSize({ risk: 30, entry: 40, stop: 10 }, 20, 'x')).toEqual({
      qty: null, text: '$20 of risk (x) buys no whole share at $30 a share.' });
    expect(proposalStageSize({ risk: null, entry: 4.38, stop: null }, 20, 'x').qty).toBeNull();
  });

  it('locks Stage first because Nova takes it, then because it is not a trade, then for what it lacks', () => {
    const size = proposalStageSize(NVXA, 20, 'x');
    expect(proposalStageLock(NVXA, size)).toBeNull();
    expect(proposalStageLock({ ...NVXA, taken_by: 'bot', not_a_trade: { reasons: ['grade C'] } }, size))
      .toBe('The bot is taking this trade: a buy of your own would double it.');
    expect(proposalStageLock({ ...NVXA, not_a_trade: { reasons: ['grade C'] } }, size)).toBe('Not a trade: grade C.');
    expect(proposalStageLock({ ...NVXA, entry: null }, size)).toMatch(/no entry price/);
    expect(proposalStageLock(NVXA, { qty: null, text: 'buys none' })).toBe('buys none');
  });

  it('stages a sub-dollar entry in four decimals, never rounded to the cent', () => {
    expect(stageLimit(0.4567)).toBe('0.4567');
    expect(stageLimit(4.38)).toBe('4.38');
    expect(stageLimit(null)).toBe('');
    const row = { ...SAMPLE_SETUPS_BOARD.rows[0], proposal: { ...NVXA, entry: 0.4567 } };
    expect(stagedLimit(row)).toBe('0.4567');
  });
});
