/**
 * What the strategies' screens say since the bots retired (ADR 072): Settings > Strategies and its template
 * editor, the Freeze card's sweep words and the day cover's alarm. The bot's API constants stay in ./bot.ts.
 */

/** The venue a gate or a line names, as the header pills say it. */
export const BOTS_VENUE_NAMES: Record<string, string> = { live: 'Live', paper: 'Paper', sim: 'Sim' };

export const botsKillSweepCancelled = (n: number, ids: string): string =>
  `cancelled ${n} order${n === 1 ? '' : 's'}${ids ? ` (${ids})` : ''}`;
export const botsKillSweepFailed = (n: number, ids: string): string =>
  `could not cancel ${n}${ids ? ` (${ids})` : ''} — still working`;
/** ADR 048: the stops that protect a held position stay resting through a freeze. */
export const botsKillSweepKept = (n: number, ids: string): string =>
  `kept ${n} protective stop${n === 1 ? '' : 's'} resting${ids ? ` (${ids})` : ''}`;
export const BOTS_KILL_SWEEP_NOTHING = 'nothing was working';

/* ---------- Templates (ADR 029): every setup's parameters and its variations ---------- */
export const BOTS_TEMPLATES_POLL_MS = 30_000;
export const BOTS_TEMPLATE_BUILTIN_WHY =
  'The default is the pre-registered rules and stays as it is -- use "New from this" to make a variation you can change';
export const BOTS_TEMPLATE_SAVING_WHY = 'Saving the last change -- wait for Nova to answer';
export const BOTS_TEMPLATE_NOTHING_CHANGED_WHY = 'Nothing changed yet -- edit a value first';
export const BOTS_TEMPLATE_UNFIXED_WHY = 'A value is out of range -- fix the field marked in red first';
export const BOTS_TEMPLATE_IN_PLAY_WHY = 'Already in play';
export const BOTS_TEMPLATE_LIMIT_WHY = (n: number): string =>
  `A setup keeps at most ${n} templates, the default included -- delete one first`;
export const BOTS_TEMPLATE_NO_PARAMS =
  'No parameters yet: this setup has never been tested. They are set when its one-second test (S5) is built.';
export const BOTS_TEMPLATE_DELETE_CONFIRM = (name: string): string =>
  `Delete "${name}"? The setups it scored stay on record; the scanner stops watching its rules.`;
export const BOTS_TEMPLATE_EVIDENCE_RESET = (name: string, rev: number, scored: number, keys: string): string =>
  `Saving new scanner rules on "${name}" (${keys}) starts its evidence over: its read-out restarts at 0 of 50, because the setups `
  + `so far were found by the old rules. The ${scored} go setup${scored === 1 ? '' : 's'} it has now stay on record under revision ${rev}.`;
export const BOTS_PARAM_FILTER_OFF_WHY = 'Off -- tick the box beside it to use this filter';

/* ---------- The day cover's alarm (ADR 048 decision 5, step 6): every desk window ---------- */
export const DAY_COVER_ALARM_TITLE = 'DAY COVER';
export const DAY_COVER_ALARM_HIDE = 'Hide 10 min';
export const DAY_COVER_ALARM_HIDE_MS = 10 * 60_000;
export const DAY_COVER_ALARM_VENUES: Record<string, string> = { live: 'Live', paper: 'Paper', sim: 'Sim' };

/* ---------- Settings > Strategies (ADR 072, approved mockup retire-bots v1) ---------- */
export const STRATEGIES_SETTINGS_NAV_LABEL = 'Strategies';
export const STRATEGIES_SETTINGS_TITLE = 'Strategies';
export const STRATEGIES_SETTINGS_BLURB =
  'Every strategy watches on Level 1, draws its setups on the charts and alerts on your stars. None places an order, '
  + 'on any venue. Each strategy\'s numbers and named templates are edited here.';
export const STRATEGIES_SETTINGS_WATCHING = 'Level 1';
export const STRATEGIES_SETTINGS_YOURS = 'yours';
export const STRATEGIES_SETTINGS_LOADING = 'Loading the strategies…';
export const STRATEGIES_SETTINGS_EDITOR_NOTE =
  'The editor keeps every number the scanner reads and your named templates. Each strategy\'s setups today are on '
  + 'Scanner > Contenders > Setups: click its number to open it there.';
export const STRATEGIES_SETTINGS_OPEN_BOARD = (label: string): string =>
  `${label}'s setups on today's board. Click to open Scanner > Contenders > Setups on ${label}, where its forming names are.`;
