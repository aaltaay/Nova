import type { BrowserExecutionTiming } from './browserTiming';

type ExecutionResultBody = {
  ok?: boolean;
};

/**
 * Parse the execution body before closing browser timing. Nova commonly
 * returns HTTP 200 for a handled execution rejection, so transport status
 * alone is not an operation outcome.
 */
export async function parseTimedExecutionResponse<
  T extends ExecutionResultBody,
>(
  response: Response,
  timing: BrowserExecutionTiming,
): Promise<T> {
  try {
    const body = await response.json() as T;
    timing.complete(response.ok && body.ok !== false);
    return body;
  } catch (error) {
    timing.complete(false);
    throw error;
  }
}
