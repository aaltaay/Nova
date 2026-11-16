/** Claude's mark: the sparkles icon on a solid coral tile (ADR 068 design; Claude's colour since ADR 072). */
import { Sparkles } from 'lucide-react';

export function ClaudeMark({ size = 16, muted = false, tone }: { size?: number; muted?: boolean; tone?: string }) {
  return (
    <span
      className={`claude-mark${muted ? ' claude-mark--muted' : ''}${tone ? ` claude-mark--${tone}` : ''}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <Sparkles size={Math.round(size * 0.64)} strokeWidth={2.4} />
    </span>
  );
}
