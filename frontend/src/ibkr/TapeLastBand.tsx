/**
 * The band over the tape (operator ask, 2026-11-06; mockup tape-align v1, option 1): the newest print's price
 * in its side's colour and its size, one line as tall as the Level 2's spread row beside it, so the two panes'
 * column heads and rows start on one line. Without a print it says a dash and keeps its height: the alignment
 * holds while the tape is empty. Its type follows the Level 2 size.
 */
import { TAPE_LAST_EMPTY, TAPE_LAST_LABEL } from '../constants';
import { useLevel2Size } from './level2Size';
import { formatTapePrice, formatTapeSize } from './TapeRow';
import type { TapePrint } from './tapeFeed';

interface Props {
  print: TapePrint | null | undefined;
}

export function TapeLastBand({ print }: Props) {
  const size = useLevel2Size();
  const side = print?.side === 'ask' || print?.side === 'bid' ? print.side : 'mid';
  return (
    <div className="l2-band ts-last" data-l2-size={size} data-testid="ts-last">
      <div className="l2-band__inner">
        <span className="l2-band__label">{TAPE_LAST_LABEL}</span>
        <span className={`l2-band__num ts-last__price ts-last__price--${side}`} data-testid="ts-last-price">
          {print ? formatTapePrice(print.price) : TAPE_LAST_EMPTY}
        </span>
        {print && <span className="ts-last__size" data-testid="ts-last-size">{formatTapeSize(print.size)}</span>}
      </div>
    </div>
  );
}
