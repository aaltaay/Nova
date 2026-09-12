/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { ChartDrawingColorPicker } from './ChartDrawingColorPicker';
import { CHART_DRAWING_COLORS } from '../chart/chartDrawingConfig';

afterEach(cleanup);

describe('ChartDrawingColorPicker', () => {
  it('renders one swatch per preset color', () => {
    render(
      <ChartDrawingColorPicker currentColor="#3b82f6" onColorChange={() => {}} />,
    );
    const swatches = screen.getAllByRole('radio');
    expect(swatches).toHaveLength(CHART_DRAWING_COLORS.length);
  });

  it('marks the current color as checked', () => {
    render(
      <ChartDrawingColorPicker currentColor="#ef4444" onColorChange={() => {}} />,
    );
    const checked = screen.getAllByRole('radio').filter(
      (el) => el.getAttribute('aria-checked') === 'true',
    );
    expect(checked).toHaveLength(1);
    expect(checked[0].getAttribute('aria-label')).toBe('#ef4444');
  });

  it('calls onColorChange when a swatch is clicked', () => {
    const onChange = vi.fn();
    render(
      <ChartDrawingColorPicker currentColor="#3b82f6" onColorChange={onChange} />,
    );
    const green = screen.getByTestId('color-swatch-22c55e');
    fireEvent.click(green);
    expect(onChange).toHaveBeenCalledWith('#22c55e');
  });

  it('applies --active class only to the current color', () => {
    render(
      <ChartDrawingColorPicker currentColor="#3b82f6" onColorChange={() => {}} />,
    );
    const swatches = screen.getAllByRole('radio');
    const activeCount = swatches.filter(
      (s) => s.classList.contains('chart-drawing-color-swatch--active'),
    ).length;
    expect(activeCount).toBe(1);
  });

  it('has a radiogroup role for accessibility', () => {
    render(
      <ChartDrawingColorPicker currentColor="#3b82f6" onColorChange={() => {}} />,
    );
    expect(screen.getByRole('radiogroup')).toBeTruthy();
  });
});
