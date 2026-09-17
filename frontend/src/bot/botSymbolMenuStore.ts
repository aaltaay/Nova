/** One floating allowlist menu for scanner rows + trader tabs. */
export type BotSymbolMenuOpen = { symbol: string; x: number; y: number } | null;

let current: BotSymbolMenuOpen = null;
const listeners = new Set<(value: BotSymbolMenuOpen) => void>();

function publish(value: BotSymbolMenuOpen): void {
  current = value;
  listeners.forEach(listener => listener(value));
}

export function openBotSymbolMenu(symbol: string, x: number, y: number): void {
  const next = symbol.trim().toUpperCase();
  if (!next) return;
  publish({ symbol: next, x, y });
}

export function closeBotSymbolMenu(): void {
  publish(null);
}

export function getBotSymbolMenu(): BotSymbolMenuOpen {
  return current;
}

export function subscribeBotSymbolMenu(
  listener: (value: BotSymbolMenuOpen) => void,
): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
