/**
 * The daily loss limit's notices in every window of the desk (ADR 056). One window reads
 * `GET /api/loss-limit` every `LOSS_LIMIT_POLL_MS` and shares the answer (ibkr's desk poll share); every
 * window raises its own notices from it (lossLimitNotices.ts), and only the window that reads says them
 * out loud, so a trip is spoken once however many windows are open. The header mute silences the voice
 * (sound/). The sample desk has no loss limit and reads nothing.
 *
 * The caller hands in where notices go (the bot's notice store, bot/BotNotices.tsx), so this feature
 * imports nothing from the Bots page.
 */
import { useEffect } from 'react';
import {
  claimDeskPollLeader,
  publishDeskPollSnap,
  readDeskPollSnap,
  subscribeDeskPollSnap,
} from '../ibkr';
import { isSampleView } from '../sample_data/sampleNav';
import { speakDesk } from '../sound';
import { fetchLossLimit, type LossLimitView } from './lossLimitApi';
import { LOSS_LIMIT_LEADER_STALE_MS, LOSS_LIMIT_POLL_SHARE } from './lossLimitNoticeWords';
import { noteLossLimit, type LossLimitNoticePush } from './lossLimitNotices';
import { LOSS_LIMIT_POLL_MS } from './lossLimitWords';

/** What the reading window shares; schema 1. */
interface LossLimitShare {
  schema_version: 1;
  view: LossLimitView;
}

function shared(raw: unknown): LossLimitView | null {
  const share = raw as LossLimitShare | null;
  if (share?.schema_version !== 1 || !share.view || typeof share.view !== 'object') return null;
  return share.view;
}

export function useLossLimitNotices(push: LossLimitNoticePush): void {
  useEffect(() => {
    if (isSampleView()) return undefined;
    let stopped = false;
    let inflight = false;

    const follow = (ts: number, raw: unknown) => {
      if (stopped || Date.now() - ts > LOSS_LIMIT_LEADER_STALE_MS) return;
      const view = shared(raw);
      if (view) noteLossLimit(view, push, null);
    };

    const poll = async () => {
      if (inflight) return;
      if (!claimDeskPollLeader(LOSS_LIMIT_POLL_SHARE, LOSS_LIMIT_LEADER_STALE_MS)) {
        // Another window reads; its answers arrive through the share. A missed one is read here.
        const env = readDeskPollSnap<LossLimitShare>(LOSS_LIMIT_POLL_SHARE);
        if (env) follow(env.ts, env.payload);
        return;
      }
      inflight = true;
      try {
        const view = await fetchLossLimit();
        if (stopped) return;
        publishDeskPollSnap<LossLimitShare>(LOSS_LIMIT_POLL_SHARE, { schema_version: 1, view });
        noteLossLimit(view, push, speakDesk);
      } catch (err) {
        // Settings > Loss limits says the read failed in words; the notices wait for the next answer.
        console.warn('[nova] the daily loss limit could not be read for its notices', err);
      } finally {
        inflight = false;
      }
    };

    const unsubscribe = subscribeDeskPollSnap<LossLimitShare>(LOSS_LIMIT_POLL_SHARE, env => follow(env.ts, env.payload));
    void poll();
    const id = window.setInterval(() => void poll(), LOSS_LIMIT_POLL_MS);
    return () => {
      stopped = true;
      window.clearInterval(id);
      unsubscribe();
    };
  }, [push]);
}
