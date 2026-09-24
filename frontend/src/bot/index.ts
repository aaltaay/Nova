/**
 * Public bot API -- cross-feature imports must use this barrel (ADR 005).
 * Kept to the symbol menu store: it imports nothing, so any list can open the
 * one right-click menu (watch list, Record, bot allowlist) without pulling
 * the Bots page in.
 */

export { closeBotSymbolMenu, openBotSymbolMenu } from './botSymbolMenuStore';
