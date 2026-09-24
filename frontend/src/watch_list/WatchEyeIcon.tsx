/** The watch list's mark: a small eye in the watch colour (currentColor). */
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
        d="M1 8s2.6-4.8 7-4.8S15 8 15 8s-2.6 4.8-7 4.8S1 8 1 8z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <circle cx="8" cy="8" r="2.2" fill="currentColor" />
    </svg>
  );
}
