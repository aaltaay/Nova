/**
 * Public bot API -- cross-feature imports must use this barrel (ADR 005).
 * Kept to the symbol menu store and the bot's notices: neither imports anything,
 * so any list can open the one right-click menu (watch list, Record, the bot's
 * stocks) and the venue pill can say what Nova cancelled when the desk left a
 * venue (ADR 042 F) without pulling the Bots page in. The Live Trader panel is the one component here, and it is
 * lazy for the same reason.
 */
import { lazy } from 'react';


export { closeBotSymbolMenu, openBotSymbolMenu } from './botSymbolMenuStore';

/** The Live Trader bots' panel (ADR 055), shown at the top of the TraderTV LIVE page. Lazy, so the barrel's other
 *  importers never load the cards: render it inside a `Suspense`. */
export const LiveTradersPanel = lazy(() => import('./BotLiveTradersCard').then(m => ({ default: m.BotLiveTradersCard })));
export { noticeVenueLeft, pushBotNotice } from './botNoticeStore';
