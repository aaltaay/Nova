/** Defense-in-depth: ignore live trades that do not match the open chart symbol. */

export function tradeMatchesChartSymbol(
  chartSymbol: string,
  tradeSymbol: string | null | undefined,
): boolean {
  if (!tradeSymbol) return true;
  return tradeSymbol.toUpperCase() === chartSymbol.toUpperCase();
}
