/**
 * Formatting utilities — dates, hashes, percentages, labels.
 * Pure functions; no React imports.
 */

// ---------------------------------------------------------------------------
// Date / time
// ---------------------------------------------------------------------------

/** Format an ISO timestamp as a readable local datetime. */
export function formatDatetime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'medium',
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

/** Format an ISO timestamp as UTC. */
export function formatUtc(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat('en-GB', {
      dateStyle: 'medium',
      timeStyle: 'long',
      timeZone: 'UTC',
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

/** Duration between two ISO timestamps. */
export function formatDuration(start: string | null, end: string | null): string {
  if (!start || !end) return '—';
  try {
    const ms = new Date(end).getTime() - new Date(start).getTime();
    if (ms < 0) return '—';
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
    const m = Math.floor(ms / 60_000);
    const s = Math.floor((ms % 60_000) / 1000);
    return `${m}m ${s}s`;
  } catch {
    return '—';
  }
}

// ---------------------------------------------------------------------------
// Hash display
// ---------------------------------------------------------------------------

/** Truncate a long hex string for display: first 8 + ... + last 8. */
export function truncateHash(hash: string | null | undefined, chars = 8): string {
  if (!hash) return '—';
  if (hash.length <= chars * 2 + 3) return hash;
  return `${hash.slice(0, chars)}…${hash.slice(-chars)}`;
}

// ---------------------------------------------------------------------------
// Percentages
// ---------------------------------------------------------------------------

/** Format a 0.0–1.0 fraction as a percentage string. */
export function formatPercent(fraction: number, decimals = 0): string {
  return `${(fraction * 100).toFixed(decimals)}%`;
}

// ---------------------------------------------------------------------------
// Label formatters
// ---------------------------------------------------------------------------

/** Convert snake_case or kebab-case to Title Case. */
export function toTitleCase(value: string | null | undefined): string {
  if (!value) return '—';
  return value
    .replace(/[_-]/g, ' ')
    .replace(/\w\S*/g, (w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase());
}

/** Map a finding category key to a display label. */
export const CATEGORY_LABELS: Record<string, string> = {
  data_integrity: 'Data Integrity',
  model_integrity: 'Model Integrity',
  inference_provenance: 'Inference Provenance',
  distribution_drift: 'Distribution Drift',
  coverage: 'Coverage Gap',
};

/** Map an evidence type key to a display label. */
export const EVIDENCE_TYPE_LABELS: Record<string, string> = {
  measurement: 'Measurement',
  comparison: 'Comparison',
  anomaly: 'Anomaly',
  hash_mismatch: 'Hash Mismatch',
  hash_match: 'Hash Match',
  statistical_test: 'Statistical Test',
  cluster: 'Cluster',
};

/** Map an audit event type to a readable label. */
export function formatAuditEventType(type: string): string {
  return type
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ');
}
