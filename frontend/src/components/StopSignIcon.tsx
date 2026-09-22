/**
 * A red stop sign: lucide's octagon as a filled plate with a white rim and
 * lucide's hand in white on it. Decorative -- the button carries the label.
 */
const PLATE =
  'M2.586 16.726A2 2 0 0 1 2 15.312V8.688a2 2 0 0 1 .586-1.414l4.688-4.688A2 2 0 0 1 8.688 2h6.624a2 2 0 0 1 1.414.586l4.688 4.688A2 2 0 0 1 22 8.688v6.624a2 2 0 0 1-.586 1.414l-4.688 4.688a2 2 0 0 1-1.414.586H8.688a2 2 0 0 1-1.414-.586z';
const HAND = [
  'M18 11V6a2 2 0 0 0-2-2a2 2 0 0 0-2 2',
  'M14 10V4a2 2 0 0 0-2-2a2 2 0 0 0-2 2v2',
  'M10 10.5V6a2 2 0 0 0-2-2a2 2 0 0 0-2 2v8',
  'M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15',
];

export function StopSignIcon({ size = 22 }: { size?: number }) {
  return (
    <svg className="stop-sign-icon" viewBox="0 0 24 24" width={size} height={size} aria-hidden="true" data-testid="stop-sign-icon">
      <path className="stop-sign-icon__plate" d={PLATE} />
      <g className="stop-sign-icon__hand" transform="translate(6.6 6.4) scale(0.45)">
        {HAND.map((d) => (
          <path key={d} d={d} />
        ))}
      </g>
    </svg>
  );
}
