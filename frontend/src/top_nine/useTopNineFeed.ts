/**
 * The pop-up's side of the boards: beat so the desk publishes, read what it sends, and keep each
 * list's rank marks (topNineMarks.nextSnapshotMarks: kept for all three lists, started over when
 * the boards' source changes between live and Sim).
 */
import { useEffect, useRef, useState } from 'react';
import { subscribeDeskPollSnap } from '../ibkr';
import {
  TOP_NINE_DESK_SILENT_MS,
  TOP_NINE_SHARE,
  TOP_NINE_VIEWER_HEARTBEAT_MS,
  type TopNineList,
} from './topNineConstants';
import {
  NO_TOP_NINE_MARKS,
  NO_TOP_NINE_STATE,
  nextSnapshotMarks,
  type TopNineMarksByList,
  type TopNineSwitch,
} from './topNineMarks';
import { parseTopNineSnapshot, type TopNineSnapshot } from './topNineSnapshot';
import { beatTopNineViewer } from './topNineViewer';

export type { TopNineMarksByList };

export interface TopNineFeedState {
  snapshot: TopNineSnapshot | null;
  /** When the desk last sent one (ms epoch), 0 before the first. */
  receivedAt: number;
  marks: TopNineMarksByList;
}

export function useTopNineFeed(onSwitch: (list: TopNineList, switched: TopNineSwitch) => void): TopNineFeedState {
  const [state, setState] = useState<TopNineFeedState>({ snapshot: null, receivedAt: 0, marks: NO_TOP_NINE_MARKS });
  const onSwitchRef = useRef(onSwitch);
  onSwitchRef.current = onSwitch;

  useEffect(() => {
    let marks = NO_TOP_NINE_STATE;
    beatTopNineViewer();
    const beat = window.setInterval(() => beatTopNineViewer(), TOP_NINE_VIEWER_HEARTBEAT_MS);
    const unsub = subscribeDeskPollSnap<unknown>(TOP_NINE_SHARE, (env) => {
      // A board left in storage by a desk that has since closed is never shown as today's.
      if (Date.now() - env.ts > TOP_NINE_DESK_SILENT_MS) return;
      const snapshot = parseTopNineSnapshot(env.payload);
      if (!snapshot) return;
      const step = nextSnapshotMarks(marks, snapshot, env.ts);
      marks = step.state;
      setState({ snapshot, receivedAt: env.ts, marks: marks.marks });
      for (const [list, switched] of step.fired) onSwitchRef.current(list, switched);
    });
    return () => {
      window.clearInterval(beat);
      unsub();
    };
  }, []);

  return state;
}
