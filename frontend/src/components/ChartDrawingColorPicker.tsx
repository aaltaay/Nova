/** Minimal color swatch bar for selected chart drawings (issue #121). */
import { CHART_DRAWING_COLORS } from '../chart/chartDrawingConfig';

interface Props {
  currentColor: string;
  onColorChange: (color: string) => void;
}

export function ChartDrawingColorPicker({ currentColor, onColorChange }: Props) {
  return (
    <div
      className="chart-drawing-color-picker"
      role="radiogroup"
      aria-label="Drawing color"
      data-testid="chart-drawing-color-picker"
    >
      {CHART_DRAWING_COLORS.map((color) => (
        <button
          key={color}
          type="button"
          role="radio"
          aria-checked={currentColor === color}
          aria-label={color}
          className={`chart-drawing-color-swatch${currentColor === color ? ' chart-drawing-color-swatch--active' : ''}`}
          style={{ ['--swatch-color' as string]: color }}
          onClick={() => onColorChange(color)}
          data-testid={`color-swatch-${color.replace('#', '')}`}
        />
      ))}
    </div>
  );
}
