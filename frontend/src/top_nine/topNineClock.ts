/** ET wall-clock text for the pop-up's clock and its switch line. Pure. */

const ET_SECONDS = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
});

/** `10:14:03` (ET) for a ms epoch. */
export function etClockSeconds(ms: number): string {
  return ET_SECONDS.format(new Date(ms));
}

/** A switch's time on the bottom line: the replay board's minute (`10:14 ET`), else when it was seen. */
export function switchClock(entry: { at: number; board?: { asOf: number; replay: boolean } }): string {
  if (entry.board?.replay) return `${etClockSeconds(entry.board.asOf * 1000).slice(0, 5)} ET`;
  return etClockSeconds(entry.at);
}
