import type { AuditEventSchema } from '../types/api';
import { formatUtc, truncateHash, formatAuditEventType } from '../lib/format';
import { CopyButton } from './CopyButton';

interface AuditEventRowProps {
  event: AuditEventSchema;
  index: number;
  isFirst: boolean;
  isInvalid?: boolean;
}

export function AuditEventRow({ event, index, isFirst, isInvalid }: AuditEventRowProps) {
  return (
    <tr className={isInvalid ? 'bg-[var(--risk-critical-bg)]' : undefined}>
      <td className="px-3 py-2.5 text-[var(--text-muted)] text-xs font-mono text-right w-8">
        {index + 1}
      </td>
      <td className="px-3 py-2.5">
        <span className="text-xs font-medium text-[var(--text-primary)]">
          {formatAuditEventType(event.event_type)}
        </span>
      </td>
      <td className="px-3 py-2.5 text-xs text-[var(--text-secondary)] whitespace-nowrap">
        {formatUtc(event.timestamp_utc)}
      </td>
      <td className="px-3 py-2.5 text-xs text-[var(--text-muted)]">
        {event.actor}
      </td>
      <td className="px-3 py-2.5">
        <div className="flex items-center gap-1">
          <code
            className="text-[10px] font-mono text-[var(--text-muted)]"
            title={event.previous_hash}
          >
            {isFirst ? (
              <span className="text-[var(--risk-none)] italic">genesis</span>
            ) : (
              truncateHash(event.previous_hash, 8)
            )}
          </code>
          <span className="text-[var(--text-muted)] text-[10px]">→</span>
          <code
            className="text-[10px] font-mono text-[var(--accent)]"
            title={event.current_hash}
          >
            {truncateHash(event.current_hash, 8)}
          </code>
          <CopyButton value={event.current_hash} title="Copy current hash" />
        </div>
      </td>
      <td className="px-3 py-2.5">
        <div className="flex items-center gap-1">
          <code
            className="text-[10px] font-mono text-[var(--text-muted)]"
            title={event.event_id}
          >
            {truncateHash(event.event_id, 8)}
          </code>
          <CopyButton value={event.event_id} title="Copy event ID" />
        </div>
      </td>
    </tr>
  );
}
