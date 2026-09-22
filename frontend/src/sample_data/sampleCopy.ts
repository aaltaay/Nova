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

/*
 * V4 (QA 2026-09-22): the sample desk sends nothing to Nova and reads only its
 * own data. The transport gate (sampleNetworkGate) answers every refused
 * request with SAMPLE_NETWORK_REFUSAL as its `detail`, so any surface that
 * prints a backend error states the refusal instead of a fault; the doors
 * below refuse earlier with copy that names what was not done.
 */
export const SAMPLE_NETWORK_REFUSAL =
  'Nova Marketing Sample Data — the sample desk sends nothing to Nova and reads only its own sample data. Exit the sample desk to use the live desk.';

/** Controls that would change the live desk (venue, bot, replay, arming). */
export const SAMPLE_WRITE_REFUSAL =
  'Nova Marketing Sample Data — this control changes the live desk, so it does nothing on the sample desk. Nothing was sent.';

/** The venue pills' one-line error slot under the header capsule. */
export const SAMPLE_VENUE_REFUSAL = 'Sample desk — venue switching is off. Nothing was sent.';

/** Level 2 / Time & Sales: the sample desk opens no live market-data line. */
export const SAMPLE_LIVE_FEED_ABSENT =
  'Nova Marketing Sample Data — no live Level 2 or tape on the sample desk.';
/** The Time & Sales head chip for that absence -- not "ERROR". */
export const SAMPLE_FEED_STATUS = 'SAMPLE';

/** Bots page and the header bot row. */
export const SAMPLE_BOT_ABSENT =
  'Nova Marketing Sample Data — bots are not part of the sample desk.';

/** Account page panels that read the practice ledger's history. */
export const SAMPLE_ACCOUNT_HISTORY_ABSENT =
  'Nova Marketing Sample Data — the sample desk has no ledger history. Exit the sample desk to see your account.';

/** Reason code on refused requests, mirroring the order doors' SAMPLE_VIEW. */
export const SAMPLE_VIEW_REASON_CODE = 'SAMPLE_VIEW';
