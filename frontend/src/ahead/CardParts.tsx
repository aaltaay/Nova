/** The pieces every Ahead panel card is built from (ADR 065): a card's head, the "AI view, not data" and exam tags, a
 * stacked bar of shares, and the way a share and a price are written. */
import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { AHEAD_COLORS, AHEAD_WORDS } from './aheadConstants';
import type { SceneChip } from './aheadSceneTypes';

export const pctText = (x: number) => `${Math.round(x * 100)}%`;
export const priceText = (p: number) => (p < 1 ? p.toFixed(4) : p.toFixed(2));

export type StackKind = 'above' | 'neither' | 'below' | 'target' | 'open' | 'stop' | 'back';

/** One stacked bar of shares (each 0-1); a share of 0 keeps no width. Colours per kind are `aheadSheet.css`'s.
 * `small`: the slimmer bar under a wall's "if it breaks" line. */
export function Stacked({ parts, testId, small = false }: {
  parts: { share: number; kind: StackKind }[];
  testId: string;
  small?: boolean;
}) {
  return (
    <div className={small ? 'ahead-stack ahead-stack--small' : 'ahead-stack'} data-testid={testId}>
      {parts.filter(p => p.share > 0).map(p => (
        <div key={p.kind} className={`ahead-stack__part ahead-stack__part--${p.kind}`} style={{ flexGrow: p.share }}>
          {pctText(p.share)}
        </div>
      ))}
    </div>
  );
}

/** A card's head: its icon and title, and the tags that say what its numbers are. */
export function CardHead({ title, icon: Icon, tag }: { title: string; icon?: LucideIcon; tag?: ReactNode }) {
  return (
    <div className="ahead-card__head">
      {Icon && <Icon className="ahead-icon" size={15} aria-hidden="true" />}
      <h3>{title}</h3>
      {tag && <span className="ahead-card__tags">{tag}</span>}
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

/** The exam's status in the chart chip's words (amber until it has passed, green once it has). */
export function ExamStatusTag({ exam }: { exam: SceneChip | null }) {
  if (!exam) return null;
  return (
    <span className="ahead-tag" data-testid="ahead-card-exam" style={{ color: exam.fg, background: exam.bg }}>
      {exam.text}
    </span>
  );
}

/** The tags a card showing AI numbers carries: "AI view, not data" and the exam's status. */
export function AiTags({ exam }: { exam: SceneChip | null }) {
  return (
    <>
      <AiTag />
      <ExamStatusTag exam={exam} />
    </>
  );
}
