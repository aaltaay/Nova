/** "Which wall first?" (ADR 061): of the forecaster's paths, the share whose minute close reaches the nearest wall
 * above first, the nearest below first, or neither in 15 minutes -- Nova's arithmetic on the AI's paths, with the
 * caveat beside it. Without the AI view it shows the walls and the reason. */
import type { ReactNode } from 'react';
import { AHEAD_COLORS, AHEAD_WORDS } from './aheadConstants';
import { etHhmm } from './aheadGeometry';
import type { AheadWalls } from './aheadTypes';

export const pctText = (x: number) => `${Math.round(x * 100)}%`;
export const priceText = (p: number) => (p < 1 ? p.toFixed(4) : p.toFixed(2));

export type StackKind = 'above' | 'neither' | 'below' | 'target' | 'open' | 'stop';

/** One stacked bar of shares (each 0-1); a share of 0 keeps no width. Colours per kind are `aheadSheet.css`'s. */
export function Stacked({ parts, testId }: { parts: { share: number; kind: StackKind }[]; testId: string }) {
  return (
    <div className="ahead-stack" data-testid={testId}>
      {parts.filter(p => p.share > 0).map(p => (
        <div key={p.kind} className={`ahead-stack__part ahead-stack__part--${p.kind}`} style={{ flexGrow: p.share }}>
          {pctText(p.share)}
        </div>
      ))}
    </div>
  );
}

/** A card's head: its title, and the tag that says what its numbers are. */
export function CardHead({ title, tag }: { title: string; tag?: ReactNode }) {
  return (
    <div className="ahead-card__head">
      <h3>{title}</h3>
      {tag}
    </div>
  );
}

export function AiTag() {
  return (
    <span className="ahead-tag" style={{ color: AHEAD_COLORS.aiTagFg, background: AHEAD_COLORS.aiTagBg }}>
      {AHEAD_WORDS.aiTag}
    </span>
  );
}

export function WallsCard({ walls, hidden, macdNote }: {
  walls: AheadWalls | null;
  /** Why the AI's odds are not shown (null when they are). */
  hidden: string | null;
  macdNote: string | null;
}) {
  const above = walls?.above ?? null;
  const below = walls?.below ?? null;
  const first = walls?.first ?? null;
  return (
    <section className="ahead-card" data-testid="ahead-walls-card">
      <CardHead title={AHEAD_WORDS.wallsTitle} tag={first ? <AiTag /> : undefined} />
      <div className="ahead-lbls">
        <span style={{ color: AHEAD_COLORS.wallAbove }}>{above ? `▲ ${priceText(above.price)} · ${above.label}` : '▲ —'}</span>
        <span className="ahead-muted">{AHEAD_WORDS.wallNeither}</span>
        <span style={{ color: AHEAD_COLORS.wallBelow }}>{below ? `▼ ${priceText(below.price)} · ${below.label}` : '▼ —'}</span>
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
        </>
      ) : (
        <p className="ahead-foot" data-testid="ahead-walls-reason">{hidden ?? walls?.reason ?? AHEAD_WORDS.noWalls}</p>
      )}
      {(first || hidden) && walls?.reason && <p className="ahead-foot">{walls.reason}</p>}
      {macdNote && <p className="ahead-foot">{macdNote}</p>}
    </section>
  );
}
