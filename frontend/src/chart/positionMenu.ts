/**
 * Chart position menu items. Only real Nova actions -- no Coming soon rows.
 * Webull Ticks Mode / Color Settings are omitted (no Nova counterpart).
 */
import {
  CHART_POSITION_MENU_CLOSE,
  CHART_POSITION_MENU_VIEW_DETAILS,
} from './positionOverlayConstants';

export type ChartPositionMenuActionId = 'close' | 'view_details';

export interface ChartPositionMenuItem {
  id: ChartPositionMenuActionId;
  label: string;
}

export function chartPositionMenuItems(): ChartPositionMenuItem[] {
  return [
    { id: 'close', label: CHART_POSITION_MENU_CLOSE },
    { id: 'view_details', label: CHART_POSITION_MENU_VIEW_DETAILS },
  ];
}
