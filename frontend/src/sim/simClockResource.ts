/**
 * One shared Sim clock poll for every consumer.
 *
 * The session header owns the clock's *controls*; anything that merely needs to
 * know what is loaded (which symbol is being replayed, whether anything is)
 * subscribes here instead of mounting a second poller or, worse, guessing.
 * Every answer -- a poll or a command reply handed in with `setData` -- passes
 * `parseSimClock`, so a malformed field reads as absent (QA 2026-09-22, C6).
 */
import { replayPollResource } from './replayPollResource';
import { SIM_HISTORY_POLL_MS } from './simConstants';
import type { SimClockState } from './simClockTypes';
import { parseSimClock } from './simPayloadParse';

export const simClockResource = replayPollResource<SimClockState>(
  '/clock',
  () => SIM_HISTORY_POLL_MS,
  { parse: parseSimClock },
);
