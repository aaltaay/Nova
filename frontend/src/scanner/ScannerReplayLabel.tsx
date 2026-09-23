/**
 * The board header's session line while the Scanner follows the Sim playhead
 * (ADR 022): `Sim · 2026-09-21 07:42 ET · recorded` (or `rebuilt`), plus the
 * reason when there is no board -- in place of `Today (Live) ▾` and today's
 * session countdown, which describe now, not the playhead.
 */
import { LEADERBOARD_LABEL_TITLE, LEADERBOARD_SOURCE_TITLE } from '../leaderboard/leaderboardConstants';
import { replayLabel, replayNotice } from '../leaderboard/leaderboardRows';
import type { ScannerReplay } from '../leaderboard/leaderboardTypes';
import '../leaderboard/leaderboardPlayback.css';

export function ScannerReplayLabel({ replay }: { replay: ScannerReplay }) {
  const notice = replayNotice(replay);
  const sourceTitle = replay.source && !replay.gap ? LEADERBOARD_SOURCE_TITLE[replay.source] : null;
  return (
    <>
      <span
        className="scanner-board__replay"
        data-testid="scanner-board-replay"
        data-source={replay.gap ? 'gap' : replay.source ?? replay.status}
        title={[LEADERBOARD_LABEL_TITLE, sourceTitle].filter(Boolean).join('\n')}
      >
        {replayLabel(replay)}
      </span>
      {notice ? (
        <>
          <span className="scanner-board__sep" aria-hidden="true">·</span>
          <span className="scanner-board__replay-gap" role="status" data-testid="scanner-board-replay-gap">
            {notice}
          </span>
        </>
      ) : null}
    </>
  );
}
