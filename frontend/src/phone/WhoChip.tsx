/**
 * The who-chip on a phone row (mockup three-books v1, phone a and c): the owner's name in the owner's colour, or
 * "Handed" in a dashed ring of the trader's colour (its trade, yours to close). Empty when the wire said nothing.
 */
import { whoChip, type Whose } from './phoneWhose';

export function WhoChip({ whose }: { whose: Whose | null }) {
  if (!whose) return <span />;
  const { text, title } = whoChip(whose);
  return (
    <span
      className="ph-who"
      data-owner={whose.owner ?? 'nova'}
      data-handed={whose.handed ? 'true' : undefined}
      title={title}
    >
      {text}
    </span>
  );
}
