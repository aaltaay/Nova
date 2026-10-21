/** "Which wall first?" (ADR 065): of the forecaster's paths, the share whose minute close reaches the nearest wall
 * above first, the nearest below first, or neither in 15 minutes -- Nova's arithmetic on the AI's paths, with the
 * caveat beside it -- and under it, what the paths do if each wall breaks (`WallBreaks`). Without the AI view it shows
 * the walls and the reason. */
import { Scale } from 'lucide-react';
import { AHEAD_COLORS, AHEAD_WORDS } from './aheadConstants';
import { etHhmm } from './aheadGeometry';
import type { SceneChip } from './aheadSceneTypes';
import type { AheadWalls } from './aheadTypes';
import { AiTags, CardHead, priceText, Stacked } from './CardParts';
import { WallBreaks } from './WallBreaks';

export function WallsCard({ walls, hidden, macdNote, exam = null }: {
  walls: AheadWalls | null;
  /** Why the AI's odds are not shown (null when they are). */
  hidden: string | null;
  macdNote: string | null;
  /** The exam's status, carried beside the AI's odds. */
  exam?: SceneChip | null;
}) {
  const above = walls?.above ?? null;
  const below = walls?.below ?? null;
  const first = walls?.first ?? null;
  return (
    <section className="ahead-card" data-testid="ahead-walls-card">
      <CardHead title={AHEAD_WORDS.wallsTitle} icon={Scale} tag={first ? <AiTags exam={exam} /> : undefined} />
      <div className="ahead-lbls">
        <span style={{ color: AHEAD_COLORS.wallAbove }} data-testid="ahead-wall-above">
          ▲ {above ? AHEAD_WORDS.wallName(priceText(above.price), above.label) : '—'}
        </span>
        <span className="ahead-muted">{AHEAD_WORDS.wallNeither}</span>
        <span style={{ color: AHEAD_COLORS.wallBelow }} data-testid="ahead-wall-below">
          ▼ {below ? AHEAD_WORDS.wallName(priceText(below.price), below.label) : '—'}
        </span>
      </div>
      {first && walls ? (
        <>
          <Stacked testId="ahead-walls-bar" parts={[
            { share: first.above ?? 0, kind: 'above' },
            { share: first.neither, kind: 'neither' },
            { share: first.below ?? 0, kind: 'below' },
          ]} />
          <p className="ahead-forecast" data-testid="ahead-walls-forecast">{AHEAD_WORDS.sharesForecast}</p>
          <p className="ahead-foot">
            {AHEAD_WORDS.wallsFoot(walls.nPaths ?? 0, walls.byT !== null ? etHhmm(walls.byT) : '—')} {AHEAD_WORDS.byNote}
          </p>
          <WallBreaks walls={walls} />
        </>
      ) : (
        <p className="ahead-foot" data-testid="ahead-walls-reason">{hidden ?? walls?.reason ?? AHEAD_WORDS.noWalls}</p>
      )}
      {(first || hidden) && walls?.reason && <p className="ahead-foot">{walls.reason}</p>}
      {macdNote && <p className="ahead-foot">{macdNote}</p>}
    </section>
  );
}
