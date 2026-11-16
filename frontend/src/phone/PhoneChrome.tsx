/**
 * The pieces every phone screen is built from (frozen mockup R2): the header's venue pill, link
 * pill and padlock, the bottom bar, the ticker chip and the banner that answers a tap.
 *
 * One rule runs through all of it: tapping a row opens the stock page, tapping the blue ticker
 * chip opens the Trader.
 */
import { useRef, useState, type ReactNode } from 'react';
import {
  ArrowLeftRight,
  Check,
  ChevronDown,
  ChevronLeft,
  Clock,
  House,
  LayoutGrid,
  Lock,
  LockOpen,
  Search,
  Wallet,
  X,
} from 'lucide-react';
import { linkText, linkTone } from './phoneLink';
import { go, goBack, type PhoneRoute, type PhoneTab } from './phoneRoute';
import { usePhoneSession } from './PhoneSession';
import { VenueMenu } from './VenueMenu';

const VENUE_WORD = { live: 'LIVE', paper: 'PAPER', sim: 'SIM' } as const;

/**
 * The desk's venue. A tap opens the venue menu under it (mockup v3): Paper, Sim and Live, and a tap on one
 * switches the desk. The menu opens on the side of the screen the pill sits on.
 */
export function VenuePill() {
  const { venue } = usePhoneSession();
  const [open, setOpen] = useState<'left' | 'right' | null>(null);
  const ref = useRef<HTMLButtonElement>(null);
  const toggle = (): void => {
    if (open) {
      setOpen(null);
      return;
    }
    // Layout px on both sides of the comparison: the frame's zoom does not move it.
    const pill = ref.current;
    const screen = pill?.closest<HTMLElement>('.ph-screen');
    setOpen(pill && screen && pill.offsetLeft > screen.offsetWidth / 2 ? 'right' : 'left');
  };
  return (
    <>
      <button
        ref={ref}
        type="button"
        className="ph-venue"
        data-venue={venue ?? 'unknown'}
        data-testid="phone-venue"
        aria-haspopup="menu"
        aria-expanded={open != null}
        aria-label={venue ? `The desk is on ${VENUE_WORD[venue]}. Switch the venue` : 'Waiting for the desk. Switch the venue'}
        onClick={toggle}
      >
        {venue ? VENUE_WORD[venue] : '…'}
        <ChevronDown size={11} strokeWidth={2.6} aria-hidden="true" className="ph-venue__chev" />
      </button>
      {open ? <VenueMenu side={open} onClose={() => setOpen(null)} /> : null}
    </>
  );
}

/** How this phone's link to the PC is doing: the middle round trip of the last 30 seconds. */
export function LinkPill({ live = false, words }: { live?: boolean; words?: string }) {
  const { link } = usePhoneSession();
  const tone = linkTone(link);
  const text = words && tone === 'good' ? words : `${live && tone === 'good' ? 'Live · ' : ''}${linkText(link)}`;
  return (
    <div className="ph-link" data-tone={tone} data-testid="phone-link" role="status" aria-label={`Link to your PC: ${text}`}>
      <i aria-hidden="true" />
      <span>{text}</span>
    </div>
  );
}

/** The desk's padlock. Green and open: orders can go. Amber and closed: nothing is sent. */
export function PadlockButton() {
  const { armed, setArmed } = usePhoneSession();
  const state = armed == null ? 'unknown' : armed ? 'true' : 'false';
  const label = armed == null
    ? 'Padlock: waiting for the desk'
    : armed ? 'Padlock open. Tap to lock' : 'Padlock locked. Tap to unlock';
  return (
    <button
      type="button"
      className="ph-icon-btn ph-padlock"
      data-armed={state}
      data-testid="phone-padlock"
      aria-label={label}
      disabled={armed == null}
      data-why={armed == null ? 'Waiting for the desk to say whether the padlock is open.' : undefined}
      onClick={() => setArmed(!armed)}
    >
      <span>{armed === false ? <Lock size={17} strokeWidth={2.2} aria-hidden="true" /> : <LockOpen size={18} aria-hidden="true" />}</span>
    </button>
  );
}

export function BackButton({ to, label }: { to: PhoneRoute; label: string }) {
  return (
    <button type="button" className="ph-icon-btn is-back" aria-label={label} onClick={() => goBack(to)}>
      <ChevronLeft size={20} aria-hidden="true" />
    </button>
  );
}

/** The blue ticker chip: opens the symbol in the Trader. */
export function TickerChip({ symbol, small = false }: { symbol: string; small?: boolean }) {
  const cls = ['ph-chip', small ? 'is-small' : '', symbol.length > 4 ? 'is-long' : ''].filter(Boolean).join(' ');
  return (
    <button
      type="button"
      className={cls}
      aria-label={`Open ${symbol} in the Trader`}
      data-testid={`phone-chip-${symbol}`}
      onClick={(ev) => {
        ev.stopPropagation();
        go({ screen: 'trade', symbol });
      }}
    >
      {symbol}
      <i aria-hidden="true">›</i>
    </button>
  );
}

/** The transparent face of a row: a tap anywhere but the chip opens the stock page. */
export function RowLink({ symbol }: { symbol: string }) {
  return (
    <button
      type="button"
      className="ph-rowlink"
      aria-label={`Open ${symbol}'s stock page`}
      onClick={() => go({ screen: 'stock', symbol })}
    />
  );
}

const TABS: readonly { tab: PhoneTab; name: string; route: PhoneRoute; icon: ReactNode }[] = [
  { tab: 'scan', name: 'Scan', route: { screen: 'scan' }, icon: <Search size={18} aria-hidden="true" /> },
  { tab: 'trade', name: 'Trade', route: { screen: 'trade', symbol: null }, icon: <ArrowLeftRight size={18} aria-hidden="true" /> },
  { tab: 'home', name: 'Home', route: { screen: 'home' }, icon: <House size={18} aria-hidden="true" /> },
  { tab: 'top9', name: 'Top 9', route: { screen: 'top9' }, icon: <LayoutGrid size={18} aria-hidden="true" /> },
  { tab: 'account', name: 'Account', route: { screen: 'account' }, icon: <Wallet size={18} aria-hidden="true" /> },
];

export function PhoneTabBar({ active }: { active: PhoneTab | null }) {
  return (
    <nav className="ph-tabs" aria-label="Screens" data-testid="phone-tabs">
      {TABS.map((t) => (
        <button
          key={t.tab}
          type="button"
          aria-current={t.tab === active ? 'page' : undefined}
          onClick={() => go(t.route)}
        >
          <span>{t.icon}</span>
          <span>{t.name}</span>
        </button>
      ))}
    </nav>
  );
}

/** What the last tap came to: sending, done, or NOT DONE in the desk's own words (that one stays until tapped). */
export function PhoneBannerView() {
  const { banner, dismissBanner } = usePhoneSession();
  if (!banner) return null;
  return (
    <button
      type="button"
      className="ph-banner"
      data-tone={banner.tone}
      data-testid="phone-banner"
      aria-live="assertive"
      onClick={() => {
        dismissBanner();
        banner.onTap?.();
      }}
    >
      <span className="ph-banner__dot" aria-hidden="true">
        {banner.tone === 'sending' ? <Clock size={18} /> : banner.tone === 'refused' ? <X size={18} strokeWidth={2.6} /> : <Check size={18} strokeWidth={2.6} />}
      </span>
      <span className="ph-banner__words">
        <span className="ph-banner__title">{banner.title}</span>
        <span className="ph-banner__note">{banner.tone === 'refused' && !banner.onTap ? `${banner.note} Tap to close.` : banner.note}</span>
      </span>
    </button>
  );
}

/** One screen: its header, its body, the bottom bar, and the banner over them. */
export function PhoneScreen({ name, header, tab, bar = true, children }: {
  name: string;
  header: ReactNode;
  tab: PhoneTab | null;
  bar?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="ph-screen" data-testid={`phone-screen-${name}`}>
      {header}
      <div className="ph-body">{children}</div>
      {bar ? <PhoneTabBar active={tab} /> : null}
      <PhoneBannerView />
    </div>
  );
}
