/**
 * Which venue the Bots page is on and what "today" is there: the header venue
 * (ADR 020), and the practice day on the venue's clock -- the replay playhead
 * on Sim, the wall clock elsewhere (QA C20 / V32).
 */
import { todayPracticeDate } from '../account/accountFigures';
import type { DeskVenue } from '../constantGroups/desk_venue';
import type { PracticeVenue } from '../constantGroups/practice';
import { resolveDeskVenue } from '../ibkr/deskVenue';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { isPracticeVenue } from '../practice/practiceAccountModel';
import { useSimAccountClock } from '../practice/useSimAccountClock';
import { useWorkspace } from '../workspace/WorkspaceContext';

export interface BotsVenue {
  venue: DeskVenue | null;
  practiceVenue: PracticeVenue | null;
  /** The venue's clock, epoch seconds. */
  nowTs: number;
  /** True when `nowTs` is the Sim playhead rather than the wall clock. */
  playhead: boolean;
  /** The practice day on that clock, YYYY-MM-DD (04:00 ET rollover). */
  today: string;
}

export function useBotsVenue(): BotsVenue {
  const { ibkrMode } = useWorkspace();
  const status = useIbkrStatus();
  const venue = resolveDeskVenue(status, ibkrMode);
  const practiceVenue = isPracticeVenue(venue) ? venue : null;
  const sim = useSimAccountClock(venue === 'sim');
  const nowTs = sim.nowTs ?? Date.now() / 1000;
  return {
    venue,
    practiceVenue,
    nowTs,
    playhead: sim.nowTs != null,
    today: todayPracticeDate(new Date(nowTs * 1000)),
  };
}
