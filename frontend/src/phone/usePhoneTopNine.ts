/**
 * The phone's Top 9 boards. The desk's pop-up is fed by the desk window, in the same browser; the
 * phone has no desk window, so it reads the same boards from its own scanner feed -- built by the
 * desk's builder (`buildTopNineSnapshot`) and marked by the desk's rule (`nextSnapshotMarks`), on
 * the cadence the desk publishes at. Nothing about a rank or a mark is decided here.
 */
import { useEffect, useRef, useState } from 'react';
import type { LiveScannerFeed } from '../scanner';
import { TOP_NINE_PUBLISH_MS, type TopNineList } from '../top_nine/topNineConstants';
import {
  NO_TOP_NINE_MARKS,
  NO_TOP_NINE_STATE,
  nextSnapshotMarks,
  type TopNineMarksByList,
  type TopNineSwitch,
} from '../top_nine/topNineMarks';
import { buildTopNineSnapshot, sameTopNine, type TopNineSnapshot } from '../top_nine/topNineSnapshot';

export interface PhoneTopNine {
  snapshot: TopNineSnapshot | null;
  marks: TopNineMarksByList;
}

export function usePhoneTopNine(
  feed: LiveScannerFeed,
  onSwitch: (list: TopNineList, switched: TopNineSwitch) => void,
): PhoneTopNine {
  const [state, setState] = useState<PhoneTopNine>({ snapshot: null, marks: NO_TOP_NINE_MARKS });
  const feedRef = useRef(feed);
  feedRef.current = feed;
  const onSwitchRef = useRef(onSwitch);
  onSwitchRef.current = onSwitch;

  useEffect(() => {
    let marks = NO_TOP_NINE_STATE;
    let last: TopNineSnapshot | null = null;
    const tick = () => {
      // Before the scanner's first answer every list is empty. Taking that as a board would mark every stock
      // "new" on the next one; the pop-up never sees it, because the desk window's feed is long loaded.
      if (feedRef.current.health.status === 'loading') return;
      const now = Date.now();
      const snapshot = buildTopNineSnapshot(feedRef.current, now);
      if (sameTopNine(last, snapshot)) return;
      last = snapshot;
      const step = nextSnapshotMarks(marks, snapshot, now);
      marks = step.state;
      setState({ snapshot, marks: marks.marks });
      for (const [list, switched] of step.fired) onSwitchRef.current(list, switched);
    };
    tick();
    const timer = window.setInterval(tick, TOP_NINE_PUBLISH_MS);
    return () => window.clearInterval(timer);
  }, []);

  return state;
}
