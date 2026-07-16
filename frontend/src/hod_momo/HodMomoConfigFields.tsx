export function NumField({
  label,
  value,
  onChange,
  step = 0.1,
  min = 0,
  hint,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
  min?: number;
  hint?: string;
}) {
  return (
    <div className="hod-cfg-field">
      <label className="hod-cfg-label" title={hint}>{label}</label>
      <input
        className="hod-cfg-input"
        type="number"
        step={step}
        min={min}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
      />
    </div>
  );
}

export function BoolField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="hod-cfg-toggle">
      <input type="checkbox" checked={value} onChange={e => onChange(e.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

export function ColorField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="hod-cfg-field hod-cfg-field--color">
      <label className="hod-cfg-label">{label}</label>
      <input
        type="color"
        value={value}
        onChange={e => onChange(e.target.value)}
        className="hod-cfg-color"
      />
      <span className="hod-cfg-color-hex">{value}</span>
    </div>
  );
}
