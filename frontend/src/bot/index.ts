/**
 * Public bot API -- cross-feature imports must use this barrel (ADR 005).
 * Kept to the symbol menu store and the bot's notices: neither imports anything,
 * so any list can open the one right-click menu (watch list, Record, the bot's
 * stocks) and the venue pill can say what Nova cancelled when the desk left a
 * venue (ADR 042 F) without pulling the Bots page in.
 */

export { closeBotSymbolMenu, openBotSymbolMenu } from './botSymbolMenuStore';
export { noticeVenueLeft, pushBotNotice } from './botNoticeStore';
