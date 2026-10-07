/**
 * LULD bands in the Level 2 book (ADR 047), as DAS draws them: a compact row of its own at the band's price,
 * in price order among a side's rows, so it never covers a size or a price. Owner: the band rows of
 * DepthLadder's MontageSide; the strip above the book is LuldStrip.tsx.
 */
import type { ReactNode } from 'react';
import { LULD_TIP_TITLE } from '../constantGroups/luld';
import { tipProps } from '../ux';
import type { PlacedMarker } from './depthMarkers';
import type { DepthLevel } from './types';

/**
 * A LULD band in the book (ADR 047), as DAS draws it: a compact row of its own at its price, so it never
 * covers a size or a price. Its word sits in the size column, which a narrow ladder keeps.
 */
function LuldRow({ marker, isBid }: { marker: PlacedMarker; isBid: boolean }) {
  const cut = marker.label.indexOf(' ');
  const word = cut > 0 ? marker.label.slice(0, cut) : marker.label;
  const price = cut > 0 ? marker.label.slice(cut + 1) : '';
  const word_ = <span className="das-l2-size das-l2-luld-word">{word}</span>;
  return (
    <div
      className={`das-l2-row das-l2-row--luld${marker.hot ? ' das-l2-row--luld-hot' : ''}`}
      data-testid={`l2-marker-${marker.id}`}
      {...tipProps(marker.tip, LULD_TIP_TITLE)}
    >
      {isBid ? (
        <>
          <span className="das-l2-mm" />
          {word_}
          <span className="das-l2-price">{price}</span>
        </>
      ) : (
        <>
          <span className="das-l2-price">{price}</span>
          {word_}
          <span className="das-l2-mm" />
        </>
      )}
    </div>
  );
}

/**
 * The side's rows with its LULD band rows in price order: before the first row worse than the band, or after
 * the last shown row when the band is deeper. Each band row takes the place of an empty padding row while one
 * is left, so a short book keeps its height.
 */
export function withBands(
  padded: readonly (DepthLevel | null)[],
  shown: number,
  bands: readonly PlacedMarker[],
  isBid: boolean,
  row: (level: DepthLevel | null, i: number) => ReactNode,
): ReactNode[] {
  if (!bands.length) return padded.map((level, i) => row(level, i));
  const at = (k: number) => bands.filter(m => m.before === k).map(m => (
    <LuldRow key={`luld-${m.id}`} marker={m} isBid={isBid} />
  ));
  let spare = bands.length;
  const out: ReactNode[] = [];
  padded.forEach((level, i) => {
    if (i <= shown) out.push(...at(i));
    if (!level && spare > 0) {
      spare -= 1;
      return;
    }
    out.push(row(level, i));
  });
  if (shown >= padded.length) out.push(...at(shown));
  return out;
}
