/**
 * Marketing copy for the sample desk (#357). Feature-local per AGENTS.md §6.1 --
 * nothing here belongs in the constants barrel.
 *
 * Wording rule: "Nova Marketing Sample Data" / "sample" only. Never fake, mock
 * or dummy -- the desk is a marketing surface, and the words ship in screenshots.
 */

export const SAMPLE_MARKETING_LABEL = 'Nova Marketing Sample Data';

/**
 * The hint must not contradict the header it sits under: SampleShell hands
 * GlobalAppBar `ibkrConnected: true`, so the bar paints a connected PAPER
 * GATEWAY chip and a funded account cluster. Saying "IBKR is not connected"
 * next to that chip reads as a bug in the screenshot this desk exists to
 * produce, so the hint states what the figures ARE instead.
 */
export const SAMPLE_MARKETING_HINT =
  'Every quote, position and figure on this desk is sample data — no live market, no real account.';

/** Returned by the order-transport guards instead of sending an order (#357). */
export const SAMPLE_ORDER_REFUSAL =
  'Nova Marketing Sample Data — Nova does not send orders from the sample desk.';

/**
 * Emergency KILL is a composite (bot L0 + desk lock + cancel-all + flatten).
 * It refuses as a whole on the sample desk, so its copy must be actionable:
 * an operator who needs a real kill has to be told where to get one, and must
 * never be left believing a real account was flattened.
 */
export const SAMPLE_KILL_REFUSAL =
  'Nova Marketing Sample Data — Emergency KILL is disabled on the sample desk and nothing was cancelled or flattened. Exit the sample desk to kill a real account.';
