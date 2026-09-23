/**
 * Nova Marketing Sample Data /api/ibkr/status (?view=sample).
 *
 * The one status the sample desk shows, wherever it is read: through
 * SampleDataProvider (useIbkrStatus) and, since V4 (QA 2026-09-22), straight
 * from the status poller on the sample route -- WorkspaceProvider and the
 * header sit above the sample shell and used to show the live venue, account
 * and Sim session under the sample banner. A connected Paper desk that
 * records nothing; types are imported type-only so this module cannot pull
 * the live poller into the graph.
 */
import type { IbkrClientStatus } from '../ibkr/ibkrStatusPoller';

export const SAMPLE_IBKR_STATUS: IbkrClientStatus = {
  enabled: true,
  connected: true,
  transport_connected: true,
  session_reason: 'ok',
  mode: 'paper',
  orders_enabled: true,
  short_enabled: true,
  spend_status: 'paper_armed',
  // An armed Paper desk: the padlock reads the latch, and the sample desk
  // never posts to it (armDesk refuses there), so the sample ticket shows Place.
  armed: true,
  armed_by: 'operator',
  arm_requires_pin: false,
  trading_allowed: true,
  trading_allowed_reason: null,
  market_data_type: 1,
  market_data_delayed: false,
  capture: false,
  recording: false,
  capture_symbol: null,
  capture_symbols: [],
  capture_sessions: [],
  capture_resume: [],
  capture_stopped: [],
  clientReady: true,
  stale: false,
  staleSince: null,
};
