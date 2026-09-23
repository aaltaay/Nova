/**
 * Nova mark used by GlobalAppBar: the app icon's eight-point star, without its
 * tile, in the current text colour (the app icon itself is
 * electron/build/icon.svg).
 */

export function NovaLogo() {
  return (
    <svg
      className="nova-logo"
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path
        fill="currentColor"
        opacity="0.55"
        d="M16.95 7.05L13.9 12L16.95 16.95L12 13.9L7.05 16.95L10.1 12L7.05 7.05L12 10.1Z"
      />
      <path
        fill="currentColor"
        d="M12 0.5L13.63 10.37L23.5 12L13.63 13.63L12 23.5L10.37 13.63L0.5 12L10.37 10.37Z"
      />
    </svg>
  );
}
