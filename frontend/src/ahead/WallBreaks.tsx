/** "If it breaks" under each wall of the walls card (ADR 065): of the forecaster's paths that close past a wall's far
 * edge, the share that reaches the next wall beyond first, the share that closes back past the near edge, and the
 * share still open -- one line and a small bar per wall, with the "not a signal" foot. Nova's arithmetic on the AI's
 * paths (`aheadBreaks.ts`); every share is a forecast. */
import { breakWords } from './aheadBreaks';
import { AHEAD_WORDS } from './aheadConstants';
import type { AheadWall, AheadWallBreak, AheadWalls } from './aheadTypes';
import { Stacked, type StackKind } from './CardParts';

function BreakRow({ wall, b, up, n }: { wall: AheadWall; b: AheadWallBreak; up: boolean; n: number }) {
  const side = up ? 'above' : 'below';
  // The bar runs in the line's order (reach the next wall, close back, still open): it has no words of its own.
  const parts: { share: number; kind: StackKind }[] = b.fail === null ? [] : [
    { share: (b.next ? b.follow : b.open) ?? 0, kind: side },
    { share: b.fail, kind: 'back' },
    ...(b.next ? [{ share: b.open ?? 0, kind: 'open' as const }] : []),
  ];
  return (
    <div className="ahead-break" data-testid={`ahead-break-${side}`}>
      <p className="ahead-break__line">{AHEAD_WORDS.breakLine(breakWords(b, wall, up, n))}</p>
      {parts.length > 0 && <Stacked small testId={`ahead-break-${side}-bar`} parts={parts} />}
    </div>
  );
}

export function WallBreaks({ walls }: { walls: AheadWalls }) {
  const breaks = walls.breaks;
  if (!breaks || (!breaks.above && !breaks.below)) return null;
  const n = walls.nPaths ?? 0;
  return (
    <div className="ahead-breaks" data-testid="ahead-breaks">
      <div className="ahead-breaks__title">{AHEAD_WORDS.breaksTitle}</div>
      {walls.above && breaks.above && <BreakRow wall={walls.above} b={breaks.above} up n={n} />}
      {walls.below && breaks.below && <BreakRow wall={walls.below} b={breaks.below} up={false} n={n} />}
      <p className="ahead-foot">{AHEAD_WORDS.breaksNote}</p>
      <p className="ahead-foot ahead-foot--signal" data-testid="ahead-breaks-foot">{AHEAD_WORDS.breaksFoot}</p>
    </div>
  );
}
