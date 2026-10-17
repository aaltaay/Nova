/**
 * Public bot API -- cross-feature imports must use this barrel (ADR 005).
 * Kept to the symbol menu store and the bot's notices: neither imports anything,
 * so any list can open the one right-click menu (watch list, Record, the bot's
 * stocks) and the venue pill can say what Nova cancelled when the desk left a
 * venue (ADR 042 F) without pulling the Bots page in. The Live Trader bots draw on Bots > LiveTrader Bots (the
 * followed traders' page, 2026-10-15), mounted by the page host, so they are not exported here.
 */
/**
 * Public bot API -- cross-feature imports must use this barrel (ADR 005).
 * Kept to the symbol menu store, the bot's notices, and the leaf API helper:
 * none of these import other features, so any list can open the one right-click
 * menu (watch list, Record, the bot's stocks) and the venue pill or kill switch
 * can reach the bot without pulling the Bots page or creating an ibkr <-> bot
 * cycle.
 */
export { closeBotSymbolMenu, openBotSymbolMenu } from './botSymbolMenuStore';
export { noticeVenueLeft, pushBotNotice } from './botNoticeStore';
export { patchBotSession } from './api';
