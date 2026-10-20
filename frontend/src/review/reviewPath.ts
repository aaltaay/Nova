/** True on the read-only historical chart route. No React, so the desk boot can branch first. */

export function isReviewPath(pathname: string): boolean {
  return pathname === '/review' || pathname.startsWith('/review/');
}
