/**
 * Marketing copy for the sample desk (#357). Feature-local per AGENTS.md §6.1 --
 * nothing here belongs in the constants barrel.
 *
 * Wording rule: "Nova Marketing Sample Data" / "sample" only. Never fake, mock
 * or dummy -- the desk is a marketing surface, and the words ship in screenshots.
 */

export const SAMPLE_MARKETING_LABEL = 'Nova Marketing Sample Data';

export const SAMPLE_MARKETING_HINT =
  'Sample fixtures only — live scanner, HOD, watchlist and IBKR feeds are not connected.';

/** Returned by the transport guard instead of sending an order (#357). */
export const SAMPLE_ORDER_REFUSAL =
  'Nova Marketing Sample Data — Nova does not send orders from the sample desk.';
