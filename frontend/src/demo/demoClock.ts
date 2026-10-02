/**
 * The demo's clock (ADR 043): the page believes it is the sample morning. `Date` starts at
 * `startMs` (09:41:27 ET on the sample day) and runs forward in real time, so the header's clock
 * ticks and the sample data's times line up for every visitor, whenever they come. Timers,
 * `performance.now()` and animation frames are untouched.
 */
export function installDemoClock(startMs: number, win: { Date: DateConstructor } = window): () => void {
  const Real = win.Date;
  const offset = startMs - Real.now();
  const now = () => Real.now() + offset;
  // A constructor function (not a subclass) so `Date()` called bare still returns a string,
  // and every Date made here is a real Date (Reflect.construct with the real constructor).
  const DemoDate = function DemoDate(this: unknown, ...args: unknown[]) {
    if (!new.target) return new Real(now()).toString();
    return Reflect.construct(Real, args.length === 0 ? [now()] : args, new.target);
  } as unknown as DateConstructor;
  Object.setPrototypeOf(DemoDate, Real); // Date.UTC and Date.parse
  Object.defineProperty(DemoDate, 'prototype', { value: Real.prototype });
  Object.defineProperty(DemoDate, 'now', { value: now });
  win.Date = DemoDate;
  return () => {
    win.Date = Real;
  };
}
