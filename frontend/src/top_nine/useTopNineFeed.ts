/**
 * The pop-up's side of the boards: beat so the desk publishes, read what it sends, and keep each
 * list's rank marks. Marks are kept for all three lists, so a tab switched to shows its recent
 * switches. A board from a different source (live <-> Sim) starts the marks over: comparing a
 * replayed minute with today's board would mark every row.
 */
import { useEffect, useRef, useState } from 'react';
import { subscribeDeskPollSnap } from '../ibkr';
import {
  TOP_NINE_DESK_SILENT_MS,
  TOP_NINE_LISTS,
  TOP_NINE_SHARE,
  TOP_NINE_VIEWER_HEARTBEAT_MS,
  type TopNineList,
} from './topNineConstants';
import {
  EMPTY_LIST_MARKS,
  nextListMarks,
  type TopNineListMarks,
  type TopNineSwitch,
} from './topNineMarks';
import { parseTopNineSnapshot, type TopNineSnapshot } from './topNineSnapshot';
import { beatTopNineViewer } from './topNineViewer';

export type TopNineMarksByList = Record<TopNineList, TopNineListMarks>;

const NO_MARKS: TopNineMarksByList = {
  gappers: EMPTY_LIST_MARKS,
  gainers: EMPTY_LIST_MARKS,
  afterhours: EMPTY_LIST_MARKS,
};

export interface TopNineFeedState {
  snapshot: TopNineSnapshot | null;
  /** When the desk last sent one (ms epoch), 0 before the first. */
  receivedAt: number;
  marks: TopNineMarksByList;
}

export function useTopNineFeed(onSwitch: (list: TopNineList, switched: TopNineSwitch) => void): TopNineFeedState {
  const [state, setState] = useState<TopNineFeedState>({ snapshot: null, receivedAt: 0, marks: NO_MARKS });
  const onSwitchRef = useRef(onSwitch);
  onSwitchRef.current = onSwitch;

  useEffect(() => {
    let marks = NO_MARKS;
    let sourceKind: string | null = null;
    beatTopNineViewer();
    const beat = window.setInterval(() => beatTopNineViewer(), TOP_NINE_VIEWER_HEARTBEAT_MS);
    const unsub = subscribeDeskPollSnap<unknown>(TOP_NINE_SHARE, (env) => {
      // A board left in storage by a desk that has since closed is never shown as today's.
      if (Date.now() - env.ts > TOP_NINE_DESK_SILENT_MS) return;
      const snapshot = parseTopNineSnapshot(env.payload);
      if (!snapshot) return;
      const fired: [TopNineList, TopNineSwitch][] = [];
      const next = { ...(sourceKind === snapshot.source.kind ? marks : NO_MARKS) };
      sourceKind = snapshot.source.kind;
      for (const { list } of TOP_NINE_LISTS) {
        const step = nextListMarks(next[list], snapshot.lists[list].rows, env.ts, {
          asOf: snapshot.asOf,
          replay: snapshot.source.kind === 'replay',
        });
        next[list] = step.state;
        if (step.switched) fired.push([list, step.switched]);
      }
      marks = next;
      setState({ snapshot, receivedAt: env.ts, marks });
      for (const [list, switched] of fired) onSwitchRef.current(list, switched);
    });
    return () => {
      window.clearInterval(beat);
      unsub();
    };
  }, []);

  return state;
}
