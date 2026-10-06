/**
 * The hot list's mark (the watch list since ADR 044): a small star in the watch colour (currentColor) --
 * filled for your ★, an outline (`hollow`) for an auto ☆.
 */
import './watchList.css';

export function WatchEyeIcon({ className = '', title, hollow = false }: { className?: string; title?: string; hollow?: boolean }) {
  return (
    <svg
      className={`watch-eye${hollow ? ' watch-eye--hollow' : ''}${className ? ` ${className}` : ''}`}
      viewBox="0 0 16 16"
      width="12"
      height="12"
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      {title ? <title>{title}</title> : null}
      <path
        d="M8 1.4l1.9 4.2 4.6.5-3.4 3.1 1 4.5L8 11.4l-4.1 2.3 1-4.5L1.5 6.1l4.6-.5z"
        fill={hollow ? 'none' : 'currentColor'}
        stroke="currentColor"
        strokeWidth={hollow ? 1.3 : 0.8}
        strokeLinejoin="round"
      />
    </svg>
  );
}
