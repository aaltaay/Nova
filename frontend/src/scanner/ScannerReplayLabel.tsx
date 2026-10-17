/**
 * The board header's session line while the Scanner follows the Sim playhead
 * (ADR 023): `Sim · 2026-09-21 07:42 ET · recorded` (or `rebuilt`), plus the
 * reason when there is no board, or on a rebuilt day where its Gappers by the second
 * stand (`Gappers by the second · 07:42:31 ET`, or the build's state) -- in place of `Today (Live) ▾` and today's
 * session countdown, which describe now, not the playhead.
 */
import {
  bySecondNotice,
  LEADERBOARD_LABEL_TITLE,
  LEADERBOARD_SECONDS_TITLE,
  LEADERBOARD_SOURCE_TITLE,
  replayLabel,
  replayNotice,
  type ScannerReplay,
} from '../leaderboard';

export function ScannerReplayLabel({ replay }: { replay: ScannerReplay }) {
  const notice = replayNotice(replay);
  const seconds = notice ? null : bySecondNotice(replay.bySecond);
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
      {seconds ? (
        <>
          <span className="scanner-board__sep" aria-hidden="true">·</span>
          <span
            className="scanner-board__replay-seconds"
            data-testid="scanner-board-replay-seconds"
            data-state={replay.bySecond?.shown ? 'shown' : replay.bySecond?.status}
            title={LEADERBOARD_SECONDS_TITLE}
          >
            {seconds}
          </span>
        </>
      ) : null}
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
