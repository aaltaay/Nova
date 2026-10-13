/**
 * What the desk toolbar adds after the indicators (the stock read's Eyes switch), for a pane's own toolbar to show
 * too: a pane in full screen covers the desk toolbar and shows its own (operator report 2026-10-13, of a 1-minute chart
 * in full screen: "i also do not see the 'eyes' button"). `ChartGrid` provides it; `TickerChartControls` shows it.
 */
import type { ReactNode } from 'react';
import { hmrStableContext } from '../utils/hmrStableContext';

export const ChartToolbarExtra = hmrStableContext<ReactNode>(import.meta.hot, 'ChartToolbarExtra');
