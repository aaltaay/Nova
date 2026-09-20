/** Session state has one mutation lane; downloads retain independent request ownership. */
let tail: Promise<void> | null = null;
const sessionPaths = new Set(['/clock', '/replay', '/history/select']);
export function serializeSimSessionMutation<T>(path: string, operation: () => Promise<T>): Promise<T> {
  if (!sessionPaths.has(path)) return operation();
  const result = tail ? tail.then(operation, operation) : operation();
  const settled = result.then(() => {}, () => {});
  tail = settled;
  void settled.then(() => { if (tail === settled) tail = null; });
  return result;
}
