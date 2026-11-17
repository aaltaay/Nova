/** The brain's mark: the brain icon on a solid purple tile (ADR 072, mockup brain-switches v1; OWNER_COLORS.brain). */
import { Brain as BrainIcon } from 'lucide-react';

export function BrainMark({ size = 16 }: { size?: number }) {
  return (
    <span className="brain-mark" style={{ width: size, height: size }} aria-hidden="true">
      <BrainIcon size={Math.round(size * 0.66)} strokeWidth={1.8} />
    </span>
  );
}
