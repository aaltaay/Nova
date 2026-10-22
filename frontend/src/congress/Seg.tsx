/** A small segmented switch (the Cryptos page's look): one choice of a few, each a real button. */
export function Seg<T extends string>({ value, options, label, onPick, testId }: {
  value: T;
  options: readonly T[];
  label: (v: T) => string;
  onPick: (v: T) => void;
  testId: string;
}) {
  return (
    <span className="cg-seg cg-push" role="group" data-testid={testId}>
      {options.map((o) => (
        <button
          type="button"
          key={o}
          className={o === value ? 'is-on' : ''}
          aria-pressed={o === value}
          onClick={() => onPick(o)}
          data-testid={`${testId}-${o}`}
        >
          {label(o)}
        </button>
      ))}
    </span>
  );
}
