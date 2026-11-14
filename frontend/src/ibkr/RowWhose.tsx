/**
 * Whose a desk positions row is (ADR 072, approved mockup three-books v1 item 6), in the Account page's chips
 * (`WhoseChip`): the holder -- You, Claude, the brain, or Earlier bots with the retired bot's name -- and, on your
 * row, the dashed chip of the shares handed to you by a switched-off trader or a retired bot ("The brain's · yours
 * to close"). Your own chip shows only while some of the row's shares are your own. The header's Positions menu,
 * the Trader's Positions tab and the Stock view draw the same chips.
 */
import { WhoseChip } from '../account';
import type { Owner } from '../constantGroups/owners';
import { ownShares, type DeskPosition } from './deskPositions';

type Row = Pick<DeskPosition, 'owner' | 'bot' | 'qty' | 'handed_qty' | 'handed_from'>;

/** Who handed you shares on your row; null when none are handed. */
export function handedOf(row: Row): Owner | null {
  return row.owner === 'you' && row.handed_from && (row.handed_qty ?? 0) !== 0 ? row.handed_from : null;
}

export function RowWhose({ row }: { row: Row }) {
  if (!row.owner) return null;
  const handed = handedOf(row);
  return (
    <span className="acct-whose-chips" data-testid="desk-whose">
      {(!handed || ownShares(row) !== 0) && <WhoseChip owner={row.owner} bot={row.bot} pill />}
      {handed && <WhoseChip owner={handed} handed pill />}
    </span>
  );
}
