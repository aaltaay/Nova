/**
 * The desk window's side of the Top 9 pop-up: while a pop-up beats, send it the first nine rows of
 * Gappers, Gainers and After Hours from this window's scanner feed -- the one feed, so the pop-up
 * never opens a scanner socket of its own. Checked every second, sent when the boards changed, and
 * at least every few seconds so the pop-up can tell a quiet board from a closed desk.
 */
import { useEffect, useRef } from 'react';
import { publishDeskPollSnap } from '../ibkr';
import { useLiveScannerFeedOptional } from '../scanner';
import {
  TOP_NINE_PUBLISH_HEARTBEAT_MS,
  TOP_NINE_PUBLISH_MS,
  TOP_NINE_SHARE,
  TOP_NINE_VIEWER_KEY,
} from './topNineConstants';
import { buildTopNineSnapshot, sameTopNine, type TopNineSnapshot } from './topNineSnapshot';
import { topNineViewerAlive } from './topNineViewer';

export function TopNinePublisher() {
  const feed = useLiveScannerFeedOptional();
  const feedRef = useRef(feed);
  feedRef.current = feed;

  useEffect(() => {
    let last: TopNineSnapshot | null = null;
    let lastAt = 0;
    const tick = () => {
      const now = Date.now();
      if (!topNineViewerAlive(now)) {
        last = null;
        return;
      }
      const snap = buildTopNineSnapshot(feedRef.current);
      if (sameTopNine(last, snap) && now - lastAt < TOP_NINE_PUBLISH_HEARTBEAT_MS) return;
      publishDeskPollSnap<TopNineSnapshot>(TOP_NINE_SHARE, snap, now);
      last = snap;
      lastAt = now;
    };
    // A pop-up that just opened beats at once: answer it without waiting for the next tick.
    const onStorage = (ev: StorageEvent) => {
      if (ev.key === TOP_NINE_VIEWER_KEY) tick();
    };
    const timer = window.setInterval(tick, TOP_NINE_PUBLISH_MS);
    window.addEventListener('storage', onStorage);
    tick();
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  return null;
}
