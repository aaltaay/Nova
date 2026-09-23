/** The Setups sub-tab's count: setups armed or near their trigger. Its own
 * component so the board's once-a-second frames re-render only this badge. */
import { useSetupsBoard } from './SetupsStreamContext';

export function SetupsTabCount() {
  const stream = useSetupsBoard();
  const live = (stream?.board?.rows ?? []).filter(r => r.state === 'near' || r.state === 'armed').length;
  if (live === 0) return null;
  return <span className="tab-count" title="Armed or near the trigger">{live}</span>;
}
