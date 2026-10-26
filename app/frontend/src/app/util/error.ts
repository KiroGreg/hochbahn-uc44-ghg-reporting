/** FastAPI errors come back as `{detail: string}` (raised via
    HTTPException) or `{detail: [{loc, msg, type}, …]}` (validation).
    Render whichever shape into a one-line message — without this
    helper, string concat on the object yields "[object Object]". */
export function formatError(e: any, fallback: string): string {
  const d = e?.error?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) {
    return d.map((x) => x?.msg ?? JSON.stringify(x)).join(' · ');
  }
  if (d && typeof d === 'object') return JSON.stringify(d);
  if (e?.message) return e.message;
  if (typeof e?.status === 'number') return `HTTP ${e.status}`;
  return fallback;
}
