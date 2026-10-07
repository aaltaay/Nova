/**
 * Test data in the backend's own shape (backend/short_proof/view.py, `GET /api/short-proof`): the Live short proof
 * as a fresh desk answers it -- margin seen, Paper reset, the tests queued, no reviewed day, no drill run, the
 * switch off. Pure data -- the tests wrap it in their own fetch mock.
 */
import type { ProofStep } from './shortProofApi';

const REVIEW_WAIT = 'No day can be marked reviewed until #778\'s question 3 (how a Paper day is reviewed) is answered.';

function step(id: string, label: string, ok: boolean | null, text: string,
  extra: Partial<ProofStep> = {}): ProofStep {
  return { id, label, ok, text, value: null, seen: 'nova', enforced: false, how: null, at: null, ...extra };
}

export function proofSteps(overrides: Partial<Record<string, Partial<ProofStep>>> = {}): ProofStep[] {
  const drill = (name: string, label: string) => step(`drill_${name}`, label, false, 'Not run yet.',
    { enforced: true, how: `Run the ${label.toLowerCase()} drill on Paper.` });
  const base: ProofStep[] = [
    step('margin_account', 'Margin account', true, 'IBKR shows a margin account.', { value: 'margin', enforced: true }),
    step('practice_reset', 'Paper reset to $5,000', true, 'Paper starts at $5,000.', { value: '$5,000' }),
    step('short_tests', 'Five-year tests run', false, '0 of 5 have a result: bear flag queued.',
      { value: '0 of 5', how: 'Run the command each short strategy\'s card names, on the desk (research/shorts).' }),
    step('paper_days', '3 Paper days with shorts, reviewed', false,
      `1 Paper day with shorts; 0 of 3 reviewed (no wrong refusal or wrong fill). ${REVIEW_WAIT}`,
      { value: '0 of 3', seen: 'operator', enforced: true,
        how: 'Short on Paper on three days; each day\'s refusals and fills are then yours to review.' }),
    drill('freeze', 'Freeze all orders with a short open'),
    drill('flatten', 'Flatten with a short open'),
    drill('day_cover', 'The 15:55 cover'),
    drill('gateway_drop', 'A Gateway drop with a short open'),
    step('live_key', 'IBKR_SHORT_ENABLED', false,
      'IBKR_SHORT_ENABLED is off. You set it last, in .env, once everything above is done.',
      { enforced: true, seen: 'operator' }),
  ];
  return base.map(s => ({ ...s, ...(overrides[s.id] ?? {}) }));
}

export function shortProofView(partial: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema_version: 1, generated_at: 1_791_400_000, complete: false,
    missing: '0 of 3 reviewed Paper days with shorts; the drills still to run on Paper: all four.',
    error: null, done: 0, total: 7, steps: proofSteps(),
    days: [{ date: '2026-10-07', shorts: 2, symbols: ['RDYN'], first_ts: null, last_ts: null, reviewed: null }],
    review: { open: false, why: REVIEW_WAIT },
    ...partial,
  };
}
