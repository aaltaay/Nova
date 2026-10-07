/** The desk's side of the agent endpoints (ADR 050): what the main window polls and how it backs off. */
export const AGENT_DESK_NEXT_PATH = '/api/agent/desk/next';
export const agentDeskReportPath = (id: string) => `/api/agent/desk/commands/${encodeURIComponent(id)}`;
/** The long poll's wait (the backend holds it at most 30 s). */
export const AGENT_DESK_POLL_WAIT_SEC = 25;
export const AGENT_DESK_FETCH_TIMEOUT_MS = 35_000;
export const AGENT_DESK_REPORT_TIMEOUT_MS = 10_000;
/** After a failed poll (Nova restarting, the network): a short wait, growing to the cap. */
export const AGENT_DESK_RETRY_MS = 5_000;
export const AGENT_DESK_RETRY_MAX_MS = 30_000;
/** An API without the agent endpoints (older backend) or without its key: ask again rarely. */
export const AGENT_DESK_UNAVAILABLE_RETRY_MS = 60_000;
/** How long a finished show's notice stays up; a failure stays until it is closed. */
export const AGENT_DESK_NOTICE_DONE_MS = 12_000;
/** The focus sensor's id for the main window (Trader pop-outs never take commands). */
export const AGENT_DESK_WINDOW_ID = 'main';

export const AGENT_DESK_TEXT = {
  heading: 'Agent',
  close: 'Close',
  done: 'On screen',
  failed: 'Could not show it',
  cancelled: 'Replaced by a newer request',
} as const;
