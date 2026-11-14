/**
 * What a freeze did on one venue, in words (D-037, ADR 042 D, ADR 048): what it cancelled, what still
 * works, the protective stops it kept resting, or why it could not read the venue. A Gateway that is down
 * is a stated failure, never "nothing to cancel". Moved from the Bots page's freeze card to the header's
 * Freeze (ADR 072).
 */
import {
  BOTS_KILL_SWEEP_NOTHING,
  BOTS_VENUE_NAMES,
  botsKillSweepCancelled,
  botsKillSweepFailed,
  botsKillSweepKept,
} from '../constantGroups/bots_page';
import type { KillSweep } from './killSwitchApi';

const ids = (list: number[]) => list.map(id => `#${id}`).join(', ');

/** The backend's " -- " read as a dash. */
const prose = (text: string): string => text.replace(/ -- /g, ' — ');

/** One venue's sweep in words: what it cancelled, what still works, or why it could not read. */
export function sweepWords(s: KillSweep): string {
  const venue = BOTS_VENUE_NAMES[s.venue] ?? s.venue;
  const parts: string[] = [];
  if (s.cancelled.length) parts.push(botsKillSweepCancelled(s.cancelled.length, ids(s.cancelled)));
  if (s.failed.length) parts.push(botsKillSweepFailed(s.failed.length, ids(s.failed)));
  if (s.kept.length) parts.push(botsKillSweepKept(s.kept.length, ids(s.kept)));
  if (s.error) parts.push(prose(s.error));
  if (!parts.length) parts.push(BOTS_KILL_SWEEP_NOTHING);
  return `${venue}: ${parts.join(' · ')}`;
}
