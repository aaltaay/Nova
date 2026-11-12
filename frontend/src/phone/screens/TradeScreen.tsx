/**
 * Trade: the order screen is the next build (ADR 070: each step is tried on the phone before the
 * next). Until it lands this screen says so plainly and points at what does send Paper orders
 * today, the link test page. Nothing here sends an order.
 */
import { ArrowLeftRight } from 'lucide-react';
import { LinkPill, PadlockButton, PhoneScreen, VenuePill } from '../PhoneChrome';
import { go } from '../phoneRoute';
import './trade.css';

export function TradeScreen({ symbol }: { symbol: string | null }) {
  return (
    <PhoneScreen
      name="trade"
      tab="trade"
      header={(
        <div className="ph-head">
          <VenuePill />
          <div className="ph-head__title">{symbol ?? 'Trade'}</div>
          <div className="ph-grow" />
          <LinkPill live />
          <PadlockButton />
        </div>
      )}
    >
      <div className="ph-trade-soon" data-testid="phone-trade-soon">
        <span className="ph-trade-soon__icon" aria-hidden="true"><ArrowLeftRight size={22} /></span>
        <b>The Trade screen is the next build</b>
        <p>
          Level 2, the tape and the one-tap ticket arrive after you have tried these screens.
          Nothing on this screen sends an order.
        </p>
        {symbol ? (
          <button type="button" className="ph-trade-soon__btn" onClick={() => go({ screen: 'stock', symbol })}>
            Open {symbol}&apos;s stock page
          </button>
        ) : null}
        <a className="ph-trade-soon__link" href="/link-test.html">Paper orders today: the link test page ›</a>
      </div>
    </PhoneScreen>
  );
}
