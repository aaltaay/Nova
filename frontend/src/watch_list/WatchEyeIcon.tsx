/** The hot list's mark (the watch list since ADR 044): a small star in the watch colour (currentColor). */
import './watchList.css';

export function WatchEyeIcon({ className = '', title }: { className?: string; title?: string }) {
  return (
    <svg
      className={`watch-eye${className ? ` ${className}` : ''}`}
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
        fill="currentColor"
        stroke="currentColor"
        strokeWidth="0.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}
