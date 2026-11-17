/**
 * What every screen shows while the PC does not answer (ADR 070; mockup v1, 2026-11-17): an amber line
 * under the header saying how old the screen is, and a sheet over the foot saying why and what to do.
 * The words are `noLinkWords.ts`; when they show is the session's (`PhoneSession.tsx`).
 */
import { ServerOff, Unplug, WifiOff, X } from 'lucide-react';
import { linkIsDown } from './phoneLink';
import { TAILSCALE_INTENT, noLinkWords, oldDataWords, type NoLinkKind } from './noLinkWords';
import { usePhoneSession } from './PhoneSession';

const ICONS: Record<NoLinkKind, typeof Unplug> = {
  offline: WifiOff,
  'nova-down': ServerOff,
  'nova-error': ServerOff,
  pc: Unplug,
};

/** Only Chrome on Android understands the link that opens another app. */
const onAndroid = (): boolean => typeof navigator !== 'undefined' && /Android/i.test(navigator.userAgent);

/** The amber line: the rows below are as old as the last answer. */
export function NoLinkLine() {
  const { link } = usePhoneSession();
  if (!linkIsDown(link)) return null;
  return (
    <div className="ph-stale" role="status" data-testid="phone-stale">
      {oldDataWords(link)}
    </div>
  );
}

/**
 * The sheet: why the PC does not answer, what to do, and that a tap may not arrive meanwhile. It locks nothing:
 * the heartbeat is one read, and an order, a sell, a Flatten or a cancel is still sent and answered in the
 * banner (ADR 045: exits always go). So it warns, and never says nothing can be sent.
 */
export function NoLinkSheet({ bar }: { bar: boolean }) {
  const { link, noLinkOpen, closeNoLink, retryLink } = usePhoneSession();
  if (!noLinkOpen) return null;
  const words = noLinkWords(link);
  const Icon = ICONS[words.kind];
  return (
    <section
      className="ph-nolink"
      data-bar={bar}
      data-kind={words.kind}
      data-testid="phone-nolink"
      role="alert"
      aria-label={words.title}
    >
      <div className="ph-nolink__head">
        <Icon size={22} aria-hidden="true" className="ph-nolink__icon" />
        <div className="ph-nolink__words">
          <span className="ph-nolink__title">{words.title}</span>
          <span className="ph-nolink__sub">{words.sub}</span>
        </div>
        <button type="button" className="ph-icon-btn" aria-label="Close" data-testid="phone-nolink-close" onClick={closeNoLink}>
          <X size={18} aria-hidden="true" />
        </button>
      </div>
      <ol className="ph-nolink__steps">
        {words.steps.map((step) => <li key={step}>{step}</li>)}
      </ol>
      <p className="ph-nolink__warn">A tap may not reach the PC until the link is back.</p>
      <div className="ph-nolink__btns">
        {words.tailscale && onAndroid() ? (
          <a className="ph-nolink__btn is-main" href={TAILSCALE_INTENT} data-testid="phone-nolink-tailscale">Open Tailscale</a>
        ) : null}
        <button type="button" className="ph-nolink__btn" data-testid="phone-nolink-retry" onClick={retryLink}>Try again</button>
      </div>
    </section>
  );
}
