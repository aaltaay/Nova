/** Webull-style chart position overlay colors (research-only visual parity). */

export const CHART_POSITION_LONG_COLOR = '#3B82F6';
export const CHART_POSITION_SHORT_COLOR = '#F43F5E';
export const CHART_POSITION_LINE_WIDTH = 1;
export const CHART_POSITION_MARKER_SIZE = 1.25;

/** Gap between the clickable badge and the right price scale. */
export const CHART_POSITION_TAG_RIGHT_GAP_PX = 6;
/** When avg-cost is off-scale (empty sample series), pin the badge here. */
export const CHART_POSITION_TAG_FALLBACK_Y_RATIO = 0.38;
/** The price scale rescales with no event to hear (autoscale, a drawing kept in view): the tag
 * measures its line again this often, and moves only when the spot changed. */
export const CHART_POSITION_TAG_REMEASURE_MS = 500;

export const CHART_POSITION_MENU_CLOSE = 'Close Position';
export const CHART_POSITION_MENU_VIEW_DETAILS = 'View Trade Details';
export const CHART_POSITION_MENU_LABEL = 'Position actions';
export const CHART_POSITION_TAG_LABEL = 'Open position';
