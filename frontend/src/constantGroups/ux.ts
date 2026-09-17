/** Global app dialog chrome — confirm / alert / prompt labels. */

export const APP_DIALOG_CONFIRM_DEFAULT_TITLE = 'Confirm';
export const APP_DIALOG_ALERT_DEFAULT_TITLE = 'Notice';
export const APP_DIALOG_PROMPT_DEFAULT_TITLE = 'Enter value';
export const APP_DIALOG_OK_LABEL = 'OK';
export const APP_DIALOG_CANCEL_LABEL = 'Cancel';
export const APP_DIALOG_CONTINUE_LABEL = 'Continue';
export const APP_DIALOG_SWITCH_LABEL = 'Switch';
export const APP_DIALOG_DELETE_LABEL = 'Delete';
export const APP_DIALOG_RESET_LABEL = 'Reset';
export const APP_DIALOG_FLATTEN_LABEL = 'Flatten';
export const APP_DIALOG_KILL_LABEL = 'Stop automation';
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
