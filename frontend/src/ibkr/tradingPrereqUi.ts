/** Open the Trading prerequisites panel from the Gateway chip (not a desk block). */
export const TRADING_PREREQ_OPEN_EVENT = 'nova-trading-prereq-open';

export function openTradingPrerequisites(): void {
  window.dispatchEvent(new Event(TRADING_PREREQ_OPEN_EVENT));
}
