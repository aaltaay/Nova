/**
 * Public bot API -- cross-feature imports must use this barrel (ADR 005).
 * ADR 072 retired the bots; what is left here: the one right-click symbol menu's store, the notices (the venue
 * pill says what Nova cancelled when the desk left a venue, ADR 042 F), and Settings > Strategies with each
 * strategy's template editor -- imported by Settings directly (bot/StrategiesSettings.tsx), so no list pulls it in.
 */
export { closeBotSymbolMenu, openBotSymbolMenu } from './botSymbolMenuStore';
export { noticeVenueLeft, pushBotNotice } from './botNoticeStore';

