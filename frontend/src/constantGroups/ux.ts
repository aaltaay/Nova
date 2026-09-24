/** Global app dialog chrome — confirm / alert / prompt labels. */

export const APP_DIALOG_CONFIRM_DEFAULT_TITLE = 'Confirm';
export const APP_DIALOG_ALERT_DEFAULT_TITLE = 'Notice';
export const APP_DIALOG_PROMPT_DEFAULT_TITLE = 'Enter value';
export const APP_DIALOG_OK_LABEL = 'OK';
export const APP_DIALOG_CANCEL_LABEL = 'Cancel';
export const APP_DIALOG_CONTINUE_LABEL = 'Continue';
export const APP_DIALOG_DELETE_LABEL = 'Delete';
export const APP_DIALOG_RESET_LABEL = 'Reset';
export const APP_DIALOG_FLATTEN_LABEL = 'Flatten';
export const APP_DIALOG_KILL_LABEL = 'Stop automation';
export const APP_DIALOG_EMERGENCY_KILL_LABEL = 'Emergency KILL';
export const APP_DIALOG_PLACE_LABEL = 'Place';
export const APP_DIALOG_FILL_LABEL = 'Fill now';
export const APP_DIALOG_SWITCH_TO_LIVE_LABEL = 'Switch to Live';
export const APP_DIALOG_SWITCH_TO_PAPER_LABEL = 'Switch to Paper';
export const IBKR_CLIENT_PORTAL_URL =
  'https://www.interactivebrokers.com/sso/Login';
export const IBKR_VERIFICATION_REQUIRED_REASON =
  'IBKR_VERIFICATION_REQUIRED';
export const IBKR_VERIFICATION_DIALOG_TITLE =
  'Order not placed -- IBKR verification required';
export const IBKR_VERIFICATION_OPEN_PORTAL_LABEL =
  'Open IBKR Client Portal';
export const IBKR_VERIFICATION_CONFIRMED_LABEL =
  "I've completed verification";

/** Place/flatten rejects -- pop-up titles (inline ticket footer is too easy to miss). */
export const ORDER_REJECT_DEFAULT_TITLE = 'Order rejected';
export const ORDER_REJECT_TITLES: Record<string, string> = {
  BUYING_POWER: 'Not enough buying power',
  BUYING_POWER_UNKNOWN: 'Buying power unavailable',
  NO_POSITION: 'No position to sell',
  OVERSELL: 'Sell quantity too large',
  ORDERS_GATE: 'Orders locked',
  MKT_OUTSIDE_RTH: 'Market orders need regular hours',
  BROKER_REJECT: 'Broker rejected the order',
  IBKR_VERIFICATION_REQUIRED: IBKR_VERIFICATION_DIALOG_TITLE,
  ACCOUNT_UNAVAILABLE: 'Account unavailable',
  POSITION_UNAVAILABLE: 'Position unavailable',
};
/** User dismissed the confirm dialog -- not a reject. */
export const ORDER_REJECT_SKIP_MESSAGES = [
  'Order cancelled',
  'Fill now cancelled',
];
/** Consecutive Nova API probe misses before auto-covering the desk (#176). */
export const DESK_API_FAIL_STREAK_FOR_OVERLAY = 3;
/** Soft IBKR warning codes -- never a reject modal (peers of Warning 2109). */
export const IBKR_SOFT_ORDER_WARNING_CODES = [
  2109, 399, 10349, 202, 2104, 2106, 2108,
] as const;

/* ---------- QA batch: orders / account / safety (2026-09-22) ---------- */
/** Error boundary copy: a view's boundary leaves the rest of the desk up... */
export const APP_ERROR_VIEW_MESSAGE = 'Something went wrong in this view. The rest of Nova may still work.';
/** ...the app-shell boundary does not -- nothing else is left on screen (C56). */
export const APP_ERROR_SHELL_MESSAGE =
  "Something went wrong in Nova's desk shell, so the rail, header and every view are down. Reload Nova to bring the desk back.";
/** The boundary source that wraps the whole desk (App.tsx). */
export const APP_ERROR_SHELL_SOURCE = 'app-shell';
/** Settings "Update & Connect" answers (C62). */
export const SETTINGS_SAVE_FAILED_TITLE = 'Settings not saved';
export const SETTINGS_SAVE_UNREACHABLE =
  'Error updating configuration. Check the API is running and try again.';
export const settingsSaveRefused = (status: number, detail: string | null): string =>
  `Nova refused the change (HTTP ${status})${detail ? `: ${detail}` : '.'} Nothing was saved.`;
