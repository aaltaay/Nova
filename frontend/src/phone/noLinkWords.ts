/**
 * What the No link sheet says (ADR 070; `architecture/schema/desk-ops.md`, "When the PC stops answering").
 * The phone names only what it can tell apart: no answer at all is "Tailscale is off on this phone" or
 * "the PC is off", and it cannot tell which, so it lists both and claims neither.
 */
import type { PhoneLinkView } from './phoneLink';

export type NoLinkKind = 'offline' | 'nova-down' | 'nova-error' | 'pc';

export interface NoLinkWords {
  kind: NoLinkKind;
  title: string;
  sub: string;
  steps: readonly string[];
  /** Offer the button that opens Tailscale: only when nothing answered, the one case it can fix. */
  tailscale: boolean;
}

/** What a tunnel answers when the program behind it is not there. */
const GATEWAY_CODES: readonly number[] = [502, 503, 504];

/** Opens the Tailscale app from Chrome on Android (its Play Store page when Chrome will not start it). */
export const TAILSCALE_INTENT = 'intent://#Intent;package=com.tailscale.ipn;end';

const BACK_BY_ITSELF = 'This screen comes back by itself.';

/** A time on this phone's clock: "5:14 AM", with the day when it is not today. */
export function clockWords(at: number, now: number): string {
  const then = new Date(at);
  const time = then.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  if (then.toDateString() === new Date(now).toDateString()) return time;
  return `${then.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}, ${time}`;
}

/** How long ago, in the sheet's words: "40 s ago", "3 min ago", "8 h 43 min ago", "2 d ago". */
export function agoWords(ms: number): string {
  const sec = Math.floor(Math.max(0, ms) / 1000);
  if (sec < 60) return `${sec} s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} min ago`;
  const hours = Math.floor(min / 60);
  if (hours < 48) return `${hours} h ${min % 60} min ago`;
  return `${Math.floor(hours / 24)} d ago`;
}

/** "Last answer 5:14 AM, 8 h 43 min ago", or that there has been none. */
export function lastAnswerWords(view: PhoneLinkView): string {
  if (view.lastAnswerAt == null) return 'No answer since this page opened';
  return `Last answer ${clockWords(view.lastAnswerAt, view.at)}, ${agoWords(view.at - view.lastAnswerAt)}`;
}

/** The amber line under every header: how old the screen is. */
export function oldDataWords(view: PhoneLinkView): string {
  if (view.lastAnswerAt == null) return 'Not live.';
  return `Showing ${clockWords(view.lastAnswerAt, view.at)}. Not live.`;
}

export function noLinkWords(view: PhoneLinkView): NoLinkWords {
  const last = lastAnswerWords(view);
  if (view.why === 'offline') {
    return {
      kind: 'offline',
      title: 'This phone is offline',
      sub: 'No Wi-Fi or mobile data',
      steps: ['Turn Wi-Fi or mobile data on.', BACK_BY_ITSELF],
      tailscale: false,
    };
  }
  if (view.why === 'nova' && view.http != null) {
    if (GATEWAY_CODES.includes(view.http)) {
      return {
        kind: 'nova-down',
        title: "Nova isn't running on the PC",
        sub: `The PC answers, Nova doesn't. ${last}`,
        steps: ['Start Nova on the PC.', BACK_BY_ITSELF],
        tailscale: false,
      };
    }
    return {
      kind: 'nova-error',
      title: 'Nova answered with an error',
      sub: `The PC's answer was ${view.http}. ${last}`,
      steps: ['Restart Nova on the PC.', BACK_BY_ITSELF],
      tailscale: false,
    };
  }
  return {
    kind: 'pc',
    title: "Can't reach your PC",
    sub: last,
    steps: ['Turn Tailscale on, on this phone.', 'Still nothing? The PC is off or asleep.'],
    tailscale: true,
  };
}
