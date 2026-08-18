/** Gate for oscillator setData -- never consume a paint key before series exist. */
export function shouldPaintOscillator(
  seriesReady: boolean,
  prevKey: string,
  paintKey: string,
): boolean {
  return seriesReady && prevKey !== paintKey;
}
