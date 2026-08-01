/**
 * Builds a same-origin URL against this app's own Route Handlers, dropping
 * undefined/empty values so an unset filter never becomes a literal
 * `?status=undefined` in the querystring. `status` is the one repeatable
 * param (mirrors `GET /runs`'s own `?status=a&status=b` convention).
 */
export function buildRunsUrl(path: string, params: Record<string, string | string[] | number | undefined>): string {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) continue;
    if (Array.isArray(value)) {
      for (const item of value) searchParams.append(key, item);
    } else {
      searchParams.set(key, String(value));
    }
  }
  const query = searchParams.toString();
  return query ? `${path}?${query}` : path;
}
